"""Target resolution: coordinates -> built-in demo targets -> Sesame -> SIMBAD TAP (ident) -> LookupError.

Built-in targets (SCIENCE_REFERENCE section 4) resolve locally first so the demo never depends on a network service.
Note: ``otype`` of built-in targets is a short descriptive text, not a SIMBAD object-type code.
"""
from __future__ import annotations

import csv
import io
import logging
import math
import re
import xml.etree.ElementTree as ET
from typing import Any, Optional
from urllib.parse import quote

import httpx

from .. import models
from ..config import get_settings
from .http import fetch

log = logging.getLogger("astra.resolver")

SESAME_URL = "https://cds.unistra.fr/cgi-bin/nph-sesame/-oxp/SNV?"
MAX_QUERY_LEN = 100

# ---------------------------------------------------------------------------------------------------- built-ins
BUILTIN_TARGETS: list[dict[str, Any]] = [
    {
        "slug": "barnard",
        "name": "Barnard's Star",
        "aliases": ["barnard", "barnard's star", "barnards star", "gj 699", "gl 699", "hip 87937", "v2500 oph"],
        "ra": 269.45208, "dec": 4.69336,
        "pm_ra": -801.6, "pm_dec": 10362.4, "parallax": 546.98, "ref_epoch": 2000.0,
        "otype": "High proper-motion M dwarf",
        "classification": "M4 V red dwarf — highest proper motion star",
        "background": (
            "Barnard's Star is an M4 V red dwarf about 1.8 pc from the Sun (parallax 546.98 mas) and has the largest "
            "proper motion of any known star, about 10.4 arcsec per year, almost entirely in declination. "
            "It is bright in the near-infrared (K about 4.5), so it saturates in most SPHEREx exposures: fluxes are "
            "lower limits and centroids near the saturated core can be biased. Over the DR1 plus QR3 baseline it moves "
            "by roughly two SPHEREx pixels, which makes it a clean test of proper-motion tracking."
        ),
        "capabilities": ["proper motion", "parallax", "saturation test"],
        "default_fov_arcmin": 3,
    },
    {
        "slug": "eps-ind-b",
        "name": "Epsilon Indi B (Ba+Bb)",
        "aliases": ["eps ind b", "eps indi b", "epsilon ind b", "epsilon indi b", "eps ind ba", "eps indi ba",
                    "epsilon indi ba", "eps ind bab", "eps indi bab", "epsilon indi bab", "eps ind ba+bb"],
        "ra": 331.04415, "dec": -56.78284,
        "pm_ra": 3982.0, "pm_dec": -2466.8, "parallax": 270.66, "ref_epoch": 2000.0,
        "otype": "Brown dwarf binary (T1+T6)",
        "classification": "T1+T6 brown-dwarf binary — fast-moving, unsaturated",
        "background": (
            "Epsilon Indi Ba and Bb form a T1 plus T6 brown-dwarf binary, unresolved at SPHEREx's 6.15 arcsec pixels, "
            "that orbits the K-type star Epsilon Indi A, which lies about 402 arcsec away. At roughly 3.7 pc with a "
            "proper motion of about 4.7 arcsec per year, it moves measurably over the survey baseline. With K about "
            "11.2 it is not saturated, so centroids and photometry are clean; methane absorption is expected near "
            "1.65, 2.2 and 3.3 micron, with a flux peak between 4 and 5 micron."
        ),
        "capabilities": ["proper motion", "unsaturated photometry", "methane spectrum"],
        "default_fov_arcmin": 3,
    },
    {
        "slug": "wise-0855",
        "name": "WISE 0855-0714",
        "aliases": ["wise 0855", "wise 0855-0714", "wise j0855-0714", "j0855-0714", "wise 0855-07",
                    "wise j085510.83-071442.5", "wisea j085510.83-071442.5", "wise 085510.83-071442.5",
                    "wise 0855 0714"],
        "ra": 133.81891, "dec": -7.24705,
        "pm_ra": -8123.7, "pm_dec": 673.2, "parallax": 439.0, "ref_epoch": 2000.0,
        "otype": "Y dwarf (brown dwarf)",
        "classification": "Y dwarf — coldest known brown dwarf, extreme proper motion",
        "background": (
            "WISE J085510.83-071442.5 is one of the coldest known brown dwarfs (spectral type Y2 in SIMBAD; Y4 in some "
            "references) at about 2.3 pc (parallax 439 mas), moving about 8.1 arcsec per year. It is extremely faint "
            "at short wavelengths and is expected to be detectable only in stacked D5 and D6 images (W2 about 13.9 "
            "Vega magnitudes), at modest signal-to-noise. The coordinates quoted in the challenge text are a "
            "WISE-era position (about 2010); by 2026 the source has moved roughly 130 arcsec, so the position must "
            "be propagated with its proper motion."
        ),
        "capabilities": ["proper motion", "coordinate epoch test", "faint-source detection"],
        "default_fov_arcmin": 3,
        "challenge_ra": 133.79513, "challenge_dec": -7.24515,
        "challenge_note": (
            "The challenge coordinates (08h55m10.831s -07d14m42.53s) are an approximately 2010-epoch WISE position. "
            "ASTRA propagates the proper motion to each SPHEREx epoch; at 2026 the source is about 130 arcsec "
            "(about 21 pixels) from that position."
        ),
    },
    {
        "slug": "rw-aur",
        "name": "RW Aurigae",
        "aliases": ["rw aur", "rw aurigae", "rw aur a", "rw aurigae a"],
        "ra": 76.95653, "dec": 30.40144,
        "pm_ra": 7.2, "pm_dec": -20.3, "parallax": None, "ref_epoch": 2000.0,
        "otype": "T Tauri star (variable)",
        "classification": "T Tauri multiple system — dimming episodes, infrared excess",
        "background": (
            "RW Aurigae is a young T Tauri multiple system (spectral type K1-5e) in the Taurus-Auriga star-forming "
            "region. It has shown deep, irregular dimming episodes attributed to circumstellar material passing in "
            "front of the star, and it has a strong infrared excess. At K about 7.0 it saturates in most SPHEREx "
            "frames, so variability tests lean on the longer-wavelength detectors and the unsaturated PSF wings."
        ),
        "capabilities": ["variability", "infrared excess", "saturation test"],
        "default_fov_arcmin": 3,
    },
    {
        "slug": "r-dra",
        "name": "R Draconis",
        "aliases": ["r dra", "r draconis"],
        "ra": 248.16761, "dec": 66.75498,
        "pm_ra": -20.6, "pm_dec": 6.1, "parallax": 1.25, "ref_epoch": 2000.0,
        "otype": "Mira variable",
        "classification": "M-type Mira variable — large-amplitude pulsation",
        "background": (
            "R Draconis is an M-type Mira variable with a pulsation period of about 245 days and a large infrared "
            "amplitude. At K about 2.2 it is very bright and saturates in most SPHEREx exposures, so its photometry "
            "is reported as lower limits. It lies at high ecliptic latitude where SPHEREx coverage is dense; visits "
            "about six months apart sample different pulsation phases, so changing H2O and CO band depths are "
            "expected."
        ),
        "capabilities": ["variability", "molecular-band spectrum", "saturation test"],
        "default_fov_arcmin": 3,
    },
]

# Epochs at which a built-in target's position is compared with a user-supplied coordinate: J2000 catalogue
# position, WISE-era (challenge text), Gaia, and the SPHEREx era.
_MATCH_EPOCHS = (2000.0, 2010.5, 2016.0, 2026.0)


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", s.lower().replace("−", "-"))


_ALIAS_INDEX: dict[str, dict[str, Any]] = {}
for _t in BUILTIN_TARGETS:
    for _a in [_t["name"], _t["slug"], *_t["aliases"]]:
        _ALIAS_INDEX[_norm(_a)] = _t


def _propagate(t: dict[str, Any], epoch: float) -> tuple[float, float]:
    """Linear proper-motion propagation of a built-in target from its J2000 position (no parallax)."""
    dt = epoch - float(t["ref_epoch"])
    dec = t["dec"] + (t["pm_dec"] or 0.0) * dt / 3.6e6
    ra = t["ra"] + (t["pm_ra"] or 0.0) * dt / 3.6e6 / max(math.cos(math.radians(t["dec"])), 1e-6)
    return ra % 360.0, dec


def _sep_arcmin(ra1: float, dec1: float, ra2: float, dec2: float) -> float:
    p1, p2 = math.radians(dec1), math.radians(dec2)
    dl = math.radians(ra1 - ra2)
    a = math.sin((p1 - p2) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return math.degrees(2 * math.asin(min(1.0, math.sqrt(a)))) * 60.0


def match_builtin(ra: float, dec: float, radius_arcmin: float = 4.0) -> dict | None:
    """Built-in target whose position (J2000, or PM-propagated to 2010.5 / 2016.0 / 2026.0) lies within
    ``radius_arcmin`` of (ra, dec); the closest wins. Lets a WISE-era coordinate be recognised as WISE 0855."""
    best: tuple[float, dict] | None = None
    for t in BUILTIN_TARGETS:
        for ep in _MATCH_EPOCHS:
            tra, tdec = _propagate(t, ep)
            s = _sep_arcmin(ra, dec, tra, tdec)
            if s <= radius_arcmin and (best is None or s < best[0]):
                best = (s, t)
    return best[1] if best else None


# ---------------------------------------------------------------------------------------------------- coordinates
_NUM = re.compile(r"^[+-]?(\d+(\.\d*)?|\.\d+)$")
_JNAME = re.compile(r"^J(\d{2})(\d{2})(\d{2}(?:\.\d+)?)([+-])(\d{2})(\d{2})(\d{2}(?:\.\d+)?)$", re.I)


def _valid(ra: float, dec: float) -> Optional[tuple[float, float]]:
    if 0.0 <= ra < 360.0 and -90.0 <= dec <= 90.0:
        return float(ra), float(dec)
    return None


def parse_coordinates(q: str) -> tuple[float, float] | None:
    """(ra_deg, dec_deg) from decimal ("133.795 -7.245", comma ok) or sexagesimal ("08 55 10.83 -07 14 42.5",
    "08h55m10.831s -7d14m42.53s", "08:55:10.8 -07:14:42", "J085510.83-071442.5"). None if not a coordinate."""
    if not q or len(q) > MAX_QUERY_LEN:
        return None
    s = q.strip().replace("−", "-")
    m = _JNAME.match(s)
    if m:
        ra = 15.0 * (int(m[1]) + int(m[2]) / 60 + float(m[3]) / 3600)
        dec = (int(m[5]) + int(m[6]) / 60 + float(m[7]) / 3600) * (-1 if m[4] == "-" else 1)
        return _valid(ra, dec)
    s2 = re.sub(r"[hHmMsSdD°'\"′″:,;]", " ", s)
    toks = s2.split()
    if not toks or any(not _NUM.match(t) for t in toks):
        return None
    if len(toks) == 2:
        return _valid(float(toks[0]), float(toks[1]))
    if len(toks) == 6 or len(toks) == 4:
        k = len(toks) // 2
        rt, dt = toks[:k], toks[k:]
        if any(t.startswith(("-", "+")) for t in rt):
            return None
        neg = dt[0].startswith("-")
        rv = [float(t) for t in rt]
        dv = [abs(float(t)) for t in dt]
        if rv[0] >= 24 or any(v >= 60 for v in rv[1:]) or any(v >= 60 for v in dv[1:]):
            return None
        ra = 15.0 * sum(v / 60 ** i for i, v in enumerate(rv))
        dec = sum(v / 60 ** i for i, v in enumerate(dv)) * (-1 if neg else 1)
        return _valid(ra, dec)
    return None


# ---------------------------------------------------------------------------------------------------- name services
def _clean_name(q: str) -> str:
    return re.sub(r"\s+", " ", q).strip()


def _float(x: Any) -> Optional[float]:
    try:
        v = float(x)
        return v if math.isfinite(v) else None
    except (TypeError, ValueError):
        return None


def parse_sesame_xml(text: str) -> Optional[dict[str, Any]]:
    """First resolver with coordinates in a Sesame ``-oxp`` response -> dict, or None."""
    root = ET.fromstring(text)
    for res in root.iter("Resolver"):
        ra, dec = _float(res.findtext("jradeg")), _float(res.findtext("jdedeg"))
        if ra is None or dec is None:
            continue
        plx = None
        plx_el = res.find("plx")
        if plx_el is not None:
            plx = _float(plx_el.findtext("v"))
        return {
            "ra": ra, "dec": dec,
            "pm_ra": _float(res.findtext("pm/pmRA")), "pm_dec": _float(res.findtext("pm/pmDE")),
            "parallax": plx, "name": (res.findtext("oname") or "").strip() or None,
            "otype": (res.findtext("otype") or "").strip() or None,
        }
    return None


async def _sesame(name: str) -> Optional[models.ResolveResult]:
    try:
        resp = await fetch("GET", SESAME_URL + quote(name, safe=""), timeout=15, retries=1)
        info = parse_sesame_xml(resp.text)
    except (httpx.HTTPError, ET.ParseError, ValueError) as e:
        log.warning("Sesame failed: %s", type(e).__name__)
        return None
    if info is None:
        return None
    return models.ResolveResult(
        query=name, name=info["name"] or name, ra=info["ra"] % 360.0, dec=info["dec"],
        pm_ra=info["pm_ra"], pm_dec=info["pm_dec"], parallax=info["parallax"], ref_epoch=2000.0,
        source="sesame", otype=info["otype"],
    )


def _adql_literal(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


async def _simbad(name: str) -> Optional[models.ResolveResult]:
    adql = (
        "SELECT TOP 1 b.main_id, b.otype, b.ra, b.dec, b.pmra, b.pmdec, b.plx_value "
        "FROM basic AS b JOIN ident AS i ON i.oidref = b.oid "
        f"WHERE i.id = {_adql_literal(name)}"
    )
    params = {"REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "csv", "QUERY": adql}
    for url in get_settings().simbad_urls:
        try:
            resp = await fetch("GET", url, params=params, timeout=10, retries=1)
            rows = list(csv.DictReader(io.StringIO(resp.text)))
        except (httpx.HTTPError, ValueError) as e:
            log.warning("SIMBAD %s failed: %s", url.split("/")[2], type(e).__name__)
            continue
        if not rows:
            return None  # SIMBAD answered: unknown identifier (no point asking the mirror)
        r = rows[0]
        ra, dec = _float(r.get("ra")), _float(r.get("dec"))
        if ra is None or dec is None:
            return None
        return models.ResolveResult(
            query=name, name=(r.get("main_id") or name).strip(), ra=ra % 360.0, dec=dec,
            pm_ra=_float(r.get("pmra")), pm_dec=_float(r.get("pmdec")), parallax=_float(r.get("plx_value")),
            ref_epoch=2000.0, source="simbad", otype=(r.get("otype") or "").strip() or None,
        )
    return None


def _from_builtin(q: str, t: dict[str, Any]) -> models.ResolveResult:
    return models.ResolveResult(
        query=q, name=t["name"], ra=t["ra"], dec=t["dec"], pm_ra=t["pm_ra"], pm_dec=t["pm_dec"],
        parallax=t["parallax"], ref_epoch=t["ref_epoch"], source="builtin", otype=t["otype"], slug=t["slug"],
        classification=t["classification"], background=t["background"], capabilities=list(t["capabilities"]),
    )


async def resolve(q: str) -> models.ResolveResult:
    """Resolve a name or coordinate string. Order: coordinates -> built-in targets -> Sesame -> SIMBAD TAP.

    A coordinate within 30 arcsec of a built-in target's J2000 / 2010.5 / 2016.0 / 2026.0 position (e.g. the
    challenge's WISE 0855 position) resolves to that built-in target (J2000 reference position + proper motion) so
    the pipeline can propagate it. Raises ``LookupError`` if nothing matches.
    """
    name = _clean_name(q or "")
    if not name or len(name) > MAX_QUERY_LEN:
        raise LookupError("empty or over-long query")
    coords = parse_coordinates(name)
    if coords is not None:
        ra, dec = coords
        hit = match_builtin(ra, dec, radius_arcmin=0.5)
        if hit is not None:
            return _from_builtin(q, hit)
        return models.ResolveResult(query=q, name=None, ra=ra, dec=dec, source="coordinates")
    t = _ALIAS_INDEX.get(_norm(name))
    if t is not None:
        return _from_builtin(q, t)
    res = await _sesame(name)
    if res is None:
        res = await _simbad(name)
    if res is None:
        raise LookupError(f"could not resolve {name!r}")
    return res
