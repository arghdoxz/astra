"""Cross-survey identification: Gaia DR3, SIMBAD, CatWISE2020 and SkyBoT (DATA_SOURCES.md section 2).

Every ``*_cone`` coroutine returns a ``CatalogResult`` and never raises: a dead service becomes
``status="unavailable"`` (timeouts, connection problems, 5xx) or ``status="error"`` (4xx, unparsable reply).

Catalog positions are propagated to the requested epoch with linear proper motion BEFORE the separation to the
query position is computed (Gaia J2016.0, SIMBAD J2000.0, CatWISE2020 MJD 57170, SkyBoT is an ephemeris computed
at the epoch). ``CatalogMatch.epoch_propagated`` is True whenever a proper-motion propagation (or ephemeris
evaluation) to the epoch was applied.  A catalog association is NOT proof of identity.

The ``parse_*`` functions are pure (text -> matches) so that they can be unit-tested offline.
"""
from __future__ import annotations

import asyncio
import csv
import io
import json
import logging
import math
from typing import Any, Optional

import httpx

from ..config import get_settings
from ..models import CatalogMatch, CatalogResult, CrossMatch
from . import cache, http

log = logging.getLogger("astra.crossmatch")

CACHE_TTL_S = 24 * 3600
MJD_J2000 = 51544.5
GAIA_REF_MJD = MJD_J2000 + 16.0 * 365.25          # J2016.0
SIMBAD_REF_MJD = MJD_J2000                         # J2000.0
CATWISE_REF_MJD = 57170.0                          # CatWISE2020 mean epoch (~2015.4)
MU_MAX_ARCSEC_YR = 10.5                            # fastest known proper motion (Barnard's Star ~10.4 "/yr)
GAIA_CAP_ARCSEC = 180.0
SIMBAD_CAP_ARCSEC = 300.0                          # SIMBAD positions are J2000 -> ~26 yr baseline
CATWISE_CAP_ARCSEC = 180.0

VARIABLE_OTYPES = frozenset({
    "V*", "Mi*", "LP*", "RR*", "Ce*", "EB*", "TT*", "Or*", "Ae*", "BY*", "RS*", "Ro*", "Pu*", "sr*", "Er*", "Fl*",
    "Y*O", "Y*?", "Ir*", "Al*", "bC*", "dS*", "gD*", "SX*", "RV*", "WV*", "El*", "FU*", "WR*", "DQ*", "CV*", "No*",
})


# --------------------------------------------------------------------------- small pure helpers
def jyear_to_mjd(jyear: float) -> float:
    return MJD_J2000 + (jyear - 2000.0) * 365.25


def angular_sep_arcsec(ra1: float, dec1: float, ra2: float, dec2: float) -> float:
    """Great-circle separation in arcsec (haversine)."""
    p1, p2 = math.radians(dec1), math.radians(dec2)
    dp = p2 - p1
    dl = math.radians(ra2 - ra1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return math.degrees(2 * math.asin(min(1.0, math.sqrt(a)))) * 3600.0


def propagate_linear(ra: float, dec: float, pm_ra: Optional[float], pm_dec: Optional[float],
                     dt_yr: float) -> tuple[float, float]:
    """Linear proper-motion propagation. pm_ra is mu_alpha* (includes cos dec), both in mas/yr."""
    if pm_ra is None or pm_dec is None or dt_yr == 0:
        return ra, dec
    cosd = max(math.cos(math.radians(dec)), 1e-6)
    new_dec = dec + pm_dec * dt_yr / 3.6e6
    new_ra = (ra + pm_ra * dt_yr / 3.6e6 / cosd) % 360.0
    return new_ra, max(-90.0, min(90.0, new_dec))


def _f(x: Any) -> Optional[float]:
    if x is None:
        return None
    s = str(x).strip()
    if s == "" or s.lower() in ("null", "none", "nan", "--"):
        return None
    try:
        v = float(s)
    except ValueError:
        return None
    return v if math.isfinite(v) else None


def _search_radius(radius_arcsec: float, ref_mjd: float, mjd: Optional[float], cap: float) -> float:
    """r_match + |mu_max| * dt allowance, capped (never below the requested radius)."""
    dt = 0.0 if mjd is None else abs(mjd - ref_mjd) / 365.25
    return max(radius_arcsec, min(cap, radius_arcsec + MU_MAX_ARCSEC_YR * dt))


def _place(ra_c: float, dec_c: float, pm_ra: Optional[float], pm_dec: Optional[float], ref_mjd: float,
           mjd: Optional[float], ra0: float, dec0: float) -> tuple[float, float, float, bool]:
    """Propagate (ra_c, dec_c) from ref_mjd to mjd; return (ra, dec, sep_to_query_arcsec, propagated)."""
    propagated = False
    ra_p, dec_p = ra_c, dec_c
    if mjd is not None and pm_ra is not None and pm_dec is not None:
        ra_p, dec_p = propagate_linear(ra_c, dec_c, pm_ra, pm_dec, (mjd - ref_mjd) / 365.25)
        propagated = True
    return ra_p, dec_p, angular_sep_arcsec(ra0, dec0, ra_p, dec_p), propagated


def _rows(text: str, required: set[str]) -> list[dict[str, str]]:
    if not text or not text.strip():
        raise ValueError("empty response")
    reader = csv.DictReader(io.StringIO(text.strip()))
    names = {(n or "").strip().lower() for n in (reader.fieldnames or [])}
    if not required <= names:
        raise ValueError(f"unexpected CSV header: {sorted(names)[:8]}")
    out = []
    for row in reader:
        out.append({(k or "").strip().lower(): (v if v is not None else "") for k, v in row.items()})
    return out


def _finish(matches: list[CatalogMatch], limit: Optional[int] = None) -> list[CatalogMatch]:
    matches.sort(key=lambda m: m.sep_arcsec)
    return matches[:limit] if limit else matches


# --------------------------------------------------------------------------- parsers (pure)
def parse_gaia_csv(text: str, ra: float, dec: float, radius_arcsec: float, mjd: Optional[float],
                   mag_range: Optional[tuple[float, float]] = None, limit: Optional[int] = None) -> list[CatalogMatch]:
    """Gaia DR3 CSV (source_id, ra, dec, pmra, pmdec, parallax, phot_g_mean_mag, phot_variable_flag).

    Rows are propagated from J2016.0 to ``mjd`` (no propagation when mjd is None) before the separation is computed.
    Keeps rows within ``radius_arcsec`` (and within ``mag_range`` G if given), sorted by separation."""
    out: list[CatalogMatch] = []
    for r in _rows(text, {"source_id", "ra", "dec"}):
        ra_c, dec_c = _f(r.get("ra")), _f(r.get("dec"))
        if ra_c is None or dec_c is None:
            continue
        pmra, pmdec = _f(r.get("pmra")), _f(r.get("pmdec"))
        g = _f(r.get("phot_g_mean_mag"))
        if mag_range is not None and (g is None or not (mag_range[0] <= g <= mag_range[1])):
            continue
        ra_p, dec_p, sep, prop = _place(ra_c, dec_c, pmra, pmdec, GAIA_REF_MJD, mjd, ra, dec)
        if sep > radius_arcsec:
            continue
        vflag = (r.get("phot_variable_flag") or "").strip() or None
        out.append(CatalogMatch(
            id=f"Gaia DR3 {r['source_id'].strip()}", ra=ra_p, dec=dec_p, sep_arcsec=round(sep, 3),
            epoch_propagated=prop, mag=g, mag_band="G" if g is not None else None,
            pm_ra=pmra, pm_dec=pmdec, parallax=_f(r.get("parallax")), variable_flag=vflag))
    return _finish(out, limit)


def parse_simbad_csv(text: str, ra: float, dec: float, radius_arcsec: float, mjd: Optional[float]) -> list[CatalogMatch]:
    """SIMBAD TAP CSV (main_id, otype, ra, dec, pmra, pmdec, plx_value); positions are J2000 -> propagated."""
    out: list[CatalogMatch] = []
    for r in _rows(text, {"main_id", "ra", "dec"}):
        ra_c, dec_c = _f(r.get("ra")), _f(r.get("dec"))
        if ra_c is None or dec_c is None:
            continue
        pmra, pmdec = _f(r.get("pmra")), _f(r.get("pmdec"))
        ra_p, dec_p, sep, prop = _place(ra_c, dec_c, pmra, pmdec, SIMBAD_REF_MJD, mjd, ra, dec)
        if sep > radius_arcsec:
            continue
        otype = (r.get("otype") or "").strip() or None
        out.append(CatalogMatch(
            id=r["main_id"].strip(), ra=ra_p, dec=dec_p, sep_arcsec=round(sep, 3), epoch_propagated=prop,
            pm_ra=pmra, pm_dec=pmdec, parallax=_f(r.get("plx_value")), otype=otype))
    return _finish(out)


def parse_catwise_csv(text: str, ra: float, dec: float, radius_arcsec: float, mjd: Optional[float]) -> list[CatalogMatch]:
    """CatWISE2020 CSV (source_name, ra, dec, pmra, pmdec, w1mpro, w2mpro). CatWISE proper motions are in
    arcsec/yr (converted to mas/yr here); positions are at MJD 57170."""
    out: list[CatalogMatch] = []
    for r in _rows(text, {"source_name", "ra", "dec"}):
        ra_c, dec_c = _f(r.get("ra")), _f(r.get("dec"))
        if ra_c is None or dec_c is None:
            continue
        pmra, pmdec = _f(r.get("pmra")), _f(r.get("pmdec"))
        pmra = pmra * 1000.0 if pmra is not None else None
        pmdec = pmdec * 1000.0 if pmdec is not None else None
        ra_p, dec_p, sep, prop = _place(ra_c, dec_c, pmra, pmdec, CATWISE_REF_MJD, mjd, ra, dec)
        if sep > radius_arcsec:
            continue
        w2, w1 = _f(r.get("w2mpro")), _f(r.get("w1mpro"))
        mag, band = (w2, "W2") if w2 is not None else ((w1, "W1") if w1 is not None else (None, None))
        out.append(CatalogMatch(
            id=r["source_name"].strip(), ra=ra_p, dec=dec_p, sep_arcsec=round(sep, 3), epoch_propagated=prop,
            mag=mag, mag_band=band, pm_ra=pmra, pm_dec=pmdec))
    return _finish(out)


def _sexagesimal(s: str, hours: bool) -> Optional[float]:
    t = s.strip().replace(":", " ").split()
    if not t:
        return None
    try:
        sign = -1.0 if t[0].startswith("-") else 1.0
        parts = [abs(float(x)) for x in t[:3]] + [0.0, 0.0]
        val = parts[0] + parts[1] / 60.0 + parts[2] / 3600.0
    except ValueError:
        return None
    return sign * val * (15.0 if hours else 1.0)


def _coord(v: Any, hours: bool) -> Optional[float]:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if " " in s or ":" in s:
        return _sexagesimal(s, hours)
    return _f(s)


def _skybot_rows(obj: Any) -> list[dict[str, Any]]:
    if isinstance(obj, dict):
        cols = obj.get("columns") or obj.get("fields")
        data = obj.get("data")
        if data is None:
            for k in ("results", "rows", "sso", "objects"):
                if k in obj:
                    data = obj[k]
                    break
        if data is None:
            return []
        if data and isinstance(data[0], (list, tuple)) and cols:
            names = [(c.get("name") if isinstance(c, dict) else str(c)) for c in cols]
            return [dict(zip(names, row)) for row in data]
        obj = data
    if isinstance(obj, list):
        return [r for r in obj if isinstance(r, dict)]
    return []


def parse_skybot_json(text: str, ra: float, dec: float, radius_arcsec: float) -> list[CatalogMatch]:
    """SkyBoT conesearch JSON -> matches within ``radius_arcsec + 3 * position error`` of the query centre.

    The reply is an ephemeris evaluated at the requested epoch, so ``epoch_propagated`` is True."""
    t = (text or "").strip()
    if not t:
        return []  # SkyBoT answers HTTP 204 with an empty body when no solar-system object is in the cone
    try:
        obj = json.loads(t)
    except ValueError:
        if "no solar system object" in t.lower() or "no object" in t.lower():
            return []
        raise ValueError("SkyBoT reply is not JSON")
    out: list[CatalogMatch] = []
    for row in _skybot_rows(obj):
        low = {str(k).strip().lower(): v for k, v in row.items()}

        def pick(pred) -> Any:
            for k, v in low.items():
                if pred(k):
                    return v
            return None

        name = pick(lambda k: k in ("name", "object", "sso_name"))
        num = pick(lambda k: k in ("num", "number", "sso_number"))
        ra_c = _coord(pick(lambda k: k.startswith("ra") and "err" not in k), hours=True)
        dec_c = _coord(pick(lambda k: k.startswith("dec") and "err" not in k), hours=False)
        if name is None or ra_c is None or dec_c is None:
            continue
        err = _f(pick(lambda k: k.startswith("err"))) or 0.0
        sep = angular_sep_arcsec(ra, dec, ra_c, dec_c)
        if sep > radius_arcsec + 3.0 * err:
            continue
        v = _f(pick(lambda k: k in ("v", "vmag") or (k.startswith("v") and "mag" in k)))
        cls = pick(lambda k: k.startswith("class"))
        numtxt = str(num).strip() if num not in (None, "", "-", 0, "0") else ""
        out.append(CatalogMatch(
            id=f"({numtxt}) {name}" if numtxt else str(name), ra=ra_c, dec=dec_c, sep_arcsec=round(sep, 3),
            epoch_propagated=True, mag=v, mag_band="V" if v is not None else None, class_=str(cls) if cls else None))
    return _finish(out)


# --------------------------------------------------------------------------- network layer
class _Unavailable(Exception):
    pass


def _classify(e: BaseException) -> tuple[str, str]:
    if isinstance(e, _Unavailable):
        return "unavailable", str(e)
    if isinstance(e, httpx.HTTPStatusError):
        code = e.response.status_code
        return ("unavailable" if code >= 500 else "error"), f"HTTP {code}"
    if isinstance(e, (httpx.TimeoutException, httpx.TransportError)):
        return "unavailable", f"{type(e).__name__}"
    if isinstance(e, ValueError):
        return "error", str(e)[:160]
    return "error", f"{type(e).__name__}: {str(e)[:120]}"


async def _get_text(url: str, params: dict[str, Any], *, timeout: float, retries: int, key: str) -> str:
    """GET with a 24 h raw-text cache (kind 'catalog'). Raises on failure."""
    try:
        hit = cache.read_json("catalog", key, CACHE_TTL_S)
    except Exception:
        hit = None
    if isinstance(hit, dict) and isinstance(hit.get("text"), str):
        return hit["text"]
    resp = await http.fetch("GET", url, params=params, timeout=timeout, retries=retries)
    text = resp.text
    try:
        cache.write_json("catalog", key, {"text": text})
    except Exception:
        log.debug("catalog cache write failed")
    return text


def _adql_params(query: str, fmt: str = "csv") -> dict[str, str]:
    return {"REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": fmt, "QUERY": query}


def _circle(ra: float, dec: float, r_arcsec: float) -> str:
    return f"CIRCLE('ICRS',{ra:.6f},{dec:.6f},{r_arcsec / 3600.0:.6f})"


async def _gaia_text(ra: float, dec: float, r_search: float, where_extra: str, top: int) -> str:
    q = (f"SELECT TOP {top} source_id, ra, dec, pmra, pmdec, parallax, phot_g_mean_mag, phot_variable_flag "
         f"FROM gaiadr3.gaia_source WHERE 1=CONTAINS(POINT('ICRS',ra,dec), {_circle(ra, dec, r_search)}){where_extra}")
    key = cache.key_of("gaia", ra, dec, r_search, where_extra, top)
    return await _get_text(get_settings().gaia_tap_url, _adql_params(q), timeout=20, retries=2, key=key)


def _result(service: str, status: str, message: Optional[str], matches: Optional[list[CatalogMatch]] = None) -> CatalogResult:
    return CatalogResult(service=service, status=status, message=message, matches=matches or [])  # type: ignore[arg-type]


async def gaia_cone(ra: float, dec: float, radius_arcsec: float, mjd: Optional[float]) -> CatalogResult:
    try:
        r_search = _search_radius(radius_arcsec, GAIA_REF_MJD, mjd, GAIA_CAP_ARCSEC)
        text = await _gaia_text(ra, dec, r_search, "", 2000)
        return _result("gaia", "ok", None, parse_gaia_csv(text, ra, dec, radius_arcsec, mjd))
    except Exception as e:  # never raise
        st, msg = _classify(e)
        return _result("gaia", st, f"Gaia DR3 {msg}")


async def simbad_cone(ra: float, dec: float, radius_arcsec: float, mjd: Optional[float]) -> CatalogResult:
    r_search = _search_radius(radius_arcsec, SIMBAD_REF_MJD, mjd, SIMBAD_CAP_ARCSEC)
    q = (f"SELECT TOP 500 main_id, otype, ra, dec, pmra, pmdec, plx_value FROM basic "
         f"WHERE CONTAINS(POINT('ICRS',ra,dec), {_circle(ra, dec, r_search)})=1")
    key = cache.key_of("simbad", ra, dec, r_search)
    last = ("unavailable", "no SIMBAD mirror configured")
    for url in get_settings().simbad_urls:
        try:
            text = await _get_text(url, _adql_params(q), timeout=10, retries=1, key=key)
            return _result("simbad", "ok", None, parse_simbad_csv(text, ra, dec, radius_arcsec, mjd))
        except Exception as e:
            last = _classify(e)
    return _result("simbad", last[0], f"SIMBAD {last[1]}")


async def catwise_cone(ra: float, dec: float, radius_arcsec: float, mjd: Optional[float]) -> CatalogResult:
    try:
        r_search = _search_radius(radius_arcsec, CATWISE_REF_MJD, mjd, CATWISE_CAP_ARCSEC)
        q = (f"SELECT TOP 300 source_name, ra, dec, pmra, pmdec, w1mpro, w2mpro FROM catwise_2020 "
             f"WHERE CONTAINS(POINT('ICRS',ra,dec), {_circle(ra, dec, r_search)})=1")
        key = cache.key_of("catwise", ra, dec, r_search)
        text = await _get_text(get_settings().irsa_tap_url, _adql_params(q), timeout=10, retries=0, key=key)
        return _result("catwise", "ok", None, parse_catwise_csv(text, ra, dec, radius_arcsec, mjd))
    except Exception as e:
        st, msg = _classify(e)
        return _result("catwise", st, f"CatWISE2020 (IRSA TAP) {msg}")


async def skybot_cone(ra: float, dec: float, radius_arcsec: float, mjd: float) -> CatalogResult:
    try:
        r_search = radius_arcsec + 10.0     # allow for the positional error filter applied in the parser
        params = {"-ep": f"{mjd + 2400000.5:.5f}", "-ra": f"{ra:.6f}", "-dec": f"{dec:.6f}",
                  "-rd": f"{r_search / 3600.0:.6f}", "-mime": "json", "-loc": "500", "-output": "basic"}
        key = cache.key_of("skybot", ra, dec, r_search, mjd)
        text = await _get_text("https://ssp.imcce.fr/webservices/skybot/api/conesearch.php", params,
                               timeout=15, retries=2, key=key)
        return _result("skybot", "ok", None, parse_skybot_json(text, ra, dec, radius_arcsec))
    except Exception as e:
        st, msg = _classify(e)
        return _result("skybot", st, f"SkyBoT {msg}")


async def crossmatch_all(ra: float, dec: float, radius_arcsec: float, mjd: float) -> CrossMatch:
    results = await asyncio.gather(
        gaia_cone(ra, dec, radius_arcsec, mjd), simbad_cone(ra, dec, radius_arcsec, mjd),
        catwise_cone(ra, dec, radius_arcsec, mjd), skybot_cone(ra, dec, radius_arcsec, mjd),
        return_exceptions=True)
    names = ("gaia", "simbad", "catwise", "skybot")
    fixed = []
    for n, r in zip(names, results):
        if isinstance(r, BaseException):
            st, msg = _classify(r)
            r = _result(n, st, f"{n} {msg}")
        fixed.append(r)
    return CrossMatch(gaia=fixed[0], simbad=fixed[1], catwise=fixed[2], skybot=fixed[3])


async def gaia_field(ra: float, dec: float, radius_arcsec: float, mjd: float, gmin: float = 10,
                     gmax: float = 16, limit: int = 50) -> list[CatalogMatch]:
    """Gaia stars with gmin <= G <= gmax within the radius, propagated to ``mjd`` (for registration checks).
    Returns [] if Gaia cannot be reached. Search radius = radius + 5 arcsec margin (registration stars are low-PM)."""
    try:
        extra = f" AND phot_g_mean_mag BETWEEN {gmin:.2f} AND {gmax:.2f}"
        text = await _gaia_text(ra, dec, radius_arcsec + 5.0, extra, 2000)
        return parse_gaia_csv(text, ra, dec, radius_arcsec, mjd, mag_range=(gmin, gmax), limit=limit)
    except Exception as e:
        log.info("gaia_field unavailable: %s", _classify(e)[1])
        return []


async def bright_stars(ra: float, dec: float, radius_arcmin: float = 2.0,
                       gmax: float = 8.0) -> Optional[list[CatalogMatch]]:
    """Gaia stars with G < gmax within radius_arcmin (J2016.0 positions, no propagation: no epoch is given).
    None when Gaia is unavailable (so 'no bright neighbour' is never claimed without data)."""
    try:
        r = radius_arcmin * 60.0
        extra = f" AND phot_g_mean_mag < {gmax:.2f}"
        text = await _gaia_text(ra, dec, r + 5.0, extra, 200)
        return parse_gaia_csv(text, ra, dec, r, None, mag_range=(-5.0, gmax))
    except Exception as e:
        log.info("bright_stars unavailable: %s", _classify(e)[1])
        return None
