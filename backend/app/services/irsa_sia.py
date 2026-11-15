"""IRSA SIA2 search for SPHEREx exposures (DATA_SOURCES section 1.2).

One VOTable row = one detector image of one exposure. ``obs_id`` is shared by the (up to 6) detector images of
the same exposure; ``did`` (``obs_publisher_did``) is the unique key per detector image.
"""
from __future__ import annotations

import asyncio
import io
import logging
import re
import warnings
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Optional

import httpx
import numpy as np

from .. import models
from . import cache
from .http import fetch

log = logging.getLogger("astra.sia")

SIA_URL = "https://irsa.ipac.caltech.edu/SIA"
SIA_TTL_S = 24 * 3600
MAXREC = 20000
_MJD_EPOCH = datetime(1858, 11, 17)

# Nominal LVF coverage per detector (um), SCIENCE_REFERENCE section 1. Only used when a row lacks em_min/em_max.
DETECTOR_BANDS: dict[int, tuple[float, float]] = {
    1: (0.75, 1.09), 2: (1.10, 1.62), 3: (1.63, 2.41), 4: (2.42, 3.82), 5: (3.83, 4.41), 6: (4.42, 5.00),
}


def mjd_to_iso(mjd: float) -> str:
    """UTC ISO-8601 string (seconds resolution) from an MJD."""
    return (_MJD_EPOCH + timedelta(days=float(mjd))).isoformat(timespec="seconds")


def collection_label(collection: str) -> str:
    """'spherex_dr1' -> 'DR1', 'spherex_qr3_deep' -> 'QR3 deep'."""
    parts = collection.replace("spherex_", "").split("_")
    return " ".join([parts[0].upper()] + parts[1:]) if parts and parts[0] else collection


# ----------------------------------------------------------------------------------------------- VOTable parsing
def _val(row: Any, col: str) -> Any:
    """Row value, or None when the column is absent / masked / NaN."""
    try:
        v = row[col]
    except (KeyError, IndexError, ValueError):
        return None
    if v is np.ma.masked:
        return None
    if isinstance(v, (bytes, np.bytes_)):
        v = v.decode("utf-8", "replace")
    if isinstance(v, (float, np.floating)) and not np.isfinite(v):
        return None
    return v


def _obs_id_from_did(did: str) -> str:
    # ivo://irsa.ipac/spherex_dr1?2025W33_2C_0321_1/D6  ->  2025W33_2C_0321_1
    q = did.split("?", 1)[-1]
    return re.sub(r"/D\d$", "", q)


def parse_sia_votable(content: bytes, collection: str) -> list[models.Exposure]:
    """Parse an SIA2 VOTable (bytes) into Exposure models (deduped by did). Raises on malformed input."""
    from astropy.io import votable

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        vt = votable.parse(io.BytesIO(content), verify="ignore")
        table = vt.get_first_table().to_table(use_names_over_ids=True)

    out: dict[str, models.Exposure] = {}
    for row in table:
        did = _val(row, "obs_publisher_did")
        access_url = _val(row, "access_url")
        t_min = _val(row, "t_min")
        band = _val(row, "energy_bandpassname")
        if not (did and access_url and t_min is not None):
            continue
        m = re.search(r"D(\d)\s*$", str(band or "")) or re.search(r"/D(\d)\s*$", str(did))
        if not m:
            continue
        det = int(m.group(1))
        did = str(did)
        if did in out:
            continue
        em_min, em_max = _val(row, "em_min"), _val(row, "em_max")
        if em_min is None or em_max is None:
            lo, hi = DETECTOR_BANDS.get(det, (float("nan"), float("nan")))
        else:
            lo, hi = float(em_min) * 1e6, float(em_max) * 1e6  # m -> um
        t_max = _val(row, "t_max")
        exptime = _val(row, "t_exptime")
        if exptime is None:
            exptime = (float(t_max) - float(t_min)) * 86400.0 if t_max is not None else 0.0
        mjd = float(t_min)
        obs_id = _val(row, "obs_id") or _obs_id_from_did(did)
        out[did] = models.Exposure(
            obs_id=str(obs_id), detector=det, did=did, collection=collection,
            mjd=mjd, date_obs=mjd_to_iso(mjd), exptime_s=float(exptime),
            em_min_um=float(lo), em_max_um=float(hi), access_url=str(access_url),
        )
    return list(out.values())


# ----------------------------------------------------------------------------------------------- queries
async def _query_one(ra: float, dec: float, collection: str) -> tuple[list[models.Exposure], str]:
    key = cache.key_of("sia", collection, ra, dec)
    cached = cache.read_json("sia", key, SIA_TTL_S)
    if cached is not None:
        try:
            return [models.Exposure(**d) for d in cached], "ok"
        except Exception:  # stale schema -> refetch
            pass
    params = {
        "COLLECTION": collection,
        "POS": f"circle {ra:.6f} {dec:.6f} 0.001",
        "RESPONSEFORMAT": "VOTABLE",
        "MAXREC": str(MAXREC),
    }
    try:
        resp = await fetch("GET", SIA_URL, params=params, timeout=90, retries=3)
    except httpx.HTTPStatusError as e:
        code = e.response.status_code
        log.warning("SIA %s HTTP %s", collection, code)
        return [], ("unavailable" if code >= 500 else "error")
    except (httpx.HTTPError, ValueError) as e:  # transport failure after retries / disallowed host
        log.warning("SIA %s failed: %s", collection, type(e).__name__)
        return [], "unavailable"
    try:
        exps = await asyncio.to_thread(parse_sia_votable, resp.content, collection)
    except Exception as e:
        log.warning("SIA %s unparsable: %s", collection, type(e).__name__)
        return [], "error"
    try:
        cache.write_json("sia", key, [e.model_dump() for e in exps])
    except OSError:
        pass
    return exps, "ok"


async def query_exposures(
    ra: float, dec: float, collections: list[str]
) -> tuple[list[models.Exposure], dict[str, str]]:
    """Exposures covering (ra, dec) in each collection; sorted by MJD, deduped by ``did``.

    Returns ``(exposures, {collection: "ok" | "unavailable" | "error"})``. One failing collection never
    affects the others.
    """
    results = await asyncio.gather(*[_query_one(ra, dec, c) for c in collections], return_exceptions=True)
    exposures: dict[str, models.Exposure] = {}
    status: dict[str, str] = {}
    for c, r in zip(collections, results):
        if isinstance(r, BaseException):
            log.warning("SIA %s raised %s", c, type(r).__name__)
            status[c] = "error"
            continue
        exps, st = r
        status[c] = st
        for e in exps:
            exposures.setdefault(e.did, e)
    return sorted(exposures.values(), key=lambda e: (e.mjd, e.detector)), status


# ----------------------------------------------------------------------------------------------- visits / sampling
def group_visits(exposures: list[models.Exposure], gap_days: float = 30) -> list[models.Visit]:
    """Split exposures (sorted by MJD) where the time gap exceeds ``gap_days``.

    Visits are numbered ``v0, v1, ...`` in time order and ``exp.visit_id`` is set in place. ``n_exposures`` counts
    detector images (Exposure objects) in the visit.
    """
    ordered = sorted(exposures, key=lambda e: (e.mjd, e.detector))
    groups: list[list[models.Exposure]] = []
    for e in ordered:
        if groups and e.mjd - groups[-1][-1].mjd <= gap_days:
            groups[-1].append(e)
        else:
            groups.append([e])
    visits: list[models.Visit] = []
    for i, g in enumerate(groups):
        vid = f"v{i}"
        counts: dict[str, int] = defaultdict(int)
        for e in g:
            e.visit_id = vid
            counts[e.collection] += 1
        coll = max(counts, key=lambda k: counts[k])
        mjds = [e.mjd for e in g]
        mean = float(np.mean(mjds))
        visits.append(models.Visit(
            id=vid, mjd_start=float(min(mjds)), mjd_end=float(max(mjds)), mjd_mean=mean,
            date_label=f"{mjd_to_iso(mean)[:7]} ({collection_label(coll)})",
            collection=coll, n_exposures=len(g), detectors=sorted({e.detector for e in g}),
        ))
    return visits


def _even_indices(n: int, q: int) -> list[int]:
    if q >= n:
        return list(range(n))
    if q <= 0:
        return []
    if q == 1:
        return [n // 2]
    return sorted({int(i) for i in np.round(np.linspace(0, n - 1, q))})


def select_exposures(
    exposures: list[models.Exposure], max_n: int, detectors: list[int]
) -> tuple[list[models.Exposure], str]:
    """Filter to ``detectors``; when more than ``max_n`` remain, sample evenly in time within each
    (visit, detector) bucket, allocating the budget proportionally (every non-empty bucket keeps >= 1 when the
    budget allows). Returns ``(selected sorted by mjd, "all" | "even_per_visit_detector")``.
    """
    det_set = set(detectors)
    pool = [e for e in exposures if e.detector in det_set]
    if len(pool) <= max_n:
        return sorted(pool, key=lambda e: (e.mjd, e.detector)), "all"
    if any(not e.visit_id for e in pool):
        group_visits(exposures)

    buckets: dict[tuple[str, int], list[models.Exposure]] = defaultdict(list)
    for e in pool:
        buckets[(e.visit_id, e.detector)].append(e)
    for b in buckets.values():
        b.sort(key=lambda e: e.mjd)
    total = len(pool)
    ideal = {k: len(v) * max_n / total for k, v in buckets.items()}
    quota = {k: min(len(buckets[k]), max(1, int(ideal[k]))) for k in buckets}
    while sum(quota.values()) > max_n:  # min-1 rule overshot the budget: trim the largest quota
        k = max(quota, key=lambda k: quota[k])
        if quota[k] <= 0:
            break
        quota[k] -= 1
    while sum(quota.values()) < max_n:  # hand out the remainder by largest shortfall
        cand = [k for k in quota if quota[k] < len(buckets[k])]
        if not cand:
            break
        k = max(cand, key=lambda k: ideal[k] - quota[k])
        quota[k] += 1

    selected: list[models.Exposure] = []
    for k, b in buckets.items():
        selected.extend(b[i] for i in _even_indices(len(b), quota[k]))
    selected.sort(key=lambda e: (e.mjd, e.detector))
    return selected, "even_per_visit_detector"
