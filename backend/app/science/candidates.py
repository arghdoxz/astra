"""Candidate detection in difference-image Z maps (SCIENCE_REFERENCE section 2.7).

Peaks of |Z| (threshold 5, 5x5 box) are found per (visit pair, detector). A positive and a negative peak within
max(3 px, 1.5 * |mu_max| * dt) form a dipole (a mover candidate); unpaired peaks are monopoles (brightness changes).
Detections are clustered within 2 px across detectors / visit pairs to count recurrence. Nothing is silently
deleted: weak or suspicious candidates are kept and carry ``rejection_reasons``.

Pixel convention: x increases WEST (east is left), y increases north. A dipole's motion is the offset from the
negative peak to the positive peak in D = S_b - S_a, divided by (t_b - t_a).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from photutils.detection import find_peaks
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree

from ..core_types import CandidateRaw, DiffContext, GridSpec

Z_THRESHOLD = 5.0
BOX_SIZE = 5
MAX_PEAKS_PER_CTX = 100
CLUSTER_RADIUS_PX = 2.0
CONTAM_RADIUS_PX = 3.0
TARGET_RADIUS_PX = 2.0
MIN_GOOD_PIXELS = 5
MAX_CANDIDATES = 25
CONTAMINATION_LABEL = "contamination"


@dataclass
class _Det:
    x: float
    y: float
    kind: str                 # "dipole" | "monopole"
    peak_z: float             # |Z| (max of the pair for dipoles)
    det: int
    pair: tuple[str, str]
    ctx: int
    pm: tuple[float, float] | None = None


def _peaks(z: np.ndarray) -> list[tuple[float, float, float]]:
    """(x, y, signed Z) of the strongest |Z| peaks >= threshold."""
    bad = ~np.isfinite(z)
    az = np.where(bad, 0.0, np.abs(z))
    tbl = find_peaks(az, threshold=Z_THRESHOLD, box_size=BOX_SIZE, mask=bad)
    if tbl is None or len(tbl) == 0:
        return []
    order = np.argsort(-np.asarray(tbl["peak_value"]))[:MAX_PEAKS_PER_CTX]
    out = []
    for i in order:
        x, y = float(tbl["x_peak"][i]), float(tbl["y_peak"][i])
        out.append((x, y, float(z[int(round(y)), int(round(x))])))
    return out


def _pair_peaks(peaks: list[tuple[float, float, float]], dt_yr: float, pixscale: float,
                max_pm_mas_yr: float) -> tuple[list[tuple[int, int, float]], set[int]]:
    """Greedy nearest-first pairing of + and - peaks. Returns ([(i_pos, i_neg, dist_px)], used_indices)."""
    radius = max(3.0, 1.5 * (max_pm_mas_yr / 1000.0) * abs(dt_yr) / pixscale)
    pos = [i for i, p in enumerate(peaks) if p[2] > 0]
    neg = [i for i, p in enumerate(peaks) if p[2] < 0]
    cands = []
    for i in pos:
        for j in neg:
            d = math.hypot(peaks[i][0] - peaks[j][0], peaks[i][1] - peaks[j][1])
            if d <= radius:
                cands.append((d, i, j))
    cands.sort()
    used: set[int] = set()
    pairs = []
    for d, i, j in cands:
        if i in used or j in used:
            continue
        used.update((i, j))
        pairs.append((i, j, d))
    return pairs, used


def _components(xy: np.ndarray) -> np.ndarray:
    n = len(xy)
    if n == 1:
        return np.zeros(1, dtype=int)
    pairs = np.array(sorted(cKDTree(xy).query_pairs(CLUSTER_RADIUS_PX)), dtype=int).reshape(-1, 2)
    if len(pairs) == 0:
        return np.arange(n)
    g = coo_matrix((np.ones(len(pairs)), (pairs[:, 0], pairs[:, 1])), shape=(n, n))
    return connected_components(g, directed=False)[1]


def _near(mask: np.ndarray, x: float, y: float, radius: float) -> bool:
    ny, nx = mask.shape
    x0, x1 = max(0, int(math.floor(x - radius))), min(nx, int(math.ceil(x + radius)) + 1)
    y0, y1 = max(0, int(math.floor(y - radius))), min(ny, int(math.ceil(y + radius)) + 1)
    if x0 >= x1 or y0 >= y1:
        return False
    yy, xx = np.mgrid[y0:y1, x0:x1]
    inside = (xx - x) ** 2 + (yy - y) ** 2 <= radius ** 2
    return bool(np.any(mask[y0:y1, x0:x1][inside]))


def _good_5x5(good: np.ndarray, x: float, y: float) -> int:
    ny, nx = good.shape
    cx, cy = int(round(x)), int(round(y))
    return int(np.count_nonzero(good[max(0, cy - 2):min(ny, cy + 3), max(0, cx - 2):min(nx, cx + 3)]))


def find_candidates(diffs: list[DiffContext], grid: GridSpec, max_pm_mas_yr: float = 10000) -> list[CandidateRaw]:
    pix = float(grid.pixscale_arcsec)
    dets: list[_Det] = []
    for ci, ctx in enumerate(diffs):
        peaks = _peaks(ctx.diff.Z)
        if not peaks:
            continue
        dt_yr = (ctx.mjd_b - ctx.mjd_a) / 365.25
        pair = (ctx.visit_a, ctx.visit_b)
        pairs, used = _pair_peaks(peaks, dt_yr, pix, max_pm_mas_yr)
        for i, j, _d in pairs:
            xp, yp, zp = peaks[i]
            xn, yn, zn = peaks[j]
            pm = None
            if abs(dt_yr) > 1e-6:
                # +x is west: dRA* = -dx * pixscale (arcsec); dDec = dy * pixscale
                pm = (-(xp - xn) * pix / dt_yr * 1000.0, (yp - yn) * pix / dt_yr * 1000.0)
            dets.append(_Det((xp + xn) / 2, (yp + yn) / 2, "dipole", max(abs(zp), abs(zn)), ctx.detector, pair, ci, pm))
        for k, (x, y, z) in enumerate(peaks):
            if k not in used:
                dets.append(_Det(x, y, "monopole", abs(z), ctx.detector, pair, ci))
    if not dets:
        return []

    labels = _components(np.array([[d.x, d.y] for d in dets], dtype=float))
    try:
        tx, ty = grid.wcs.world_to_pixel_values(grid.ra, grid.dec)
        tx, ty = float(tx), float(ty)
    except Exception:
        tx, ty = (grid.shape[1] - 1) / 2.0, (grid.shape[0] - 1) / 2.0

    raws: list[CandidateRaw] = []
    for lab in np.unique(labels):
        members = [d for d, l in zip(dets, labels) if l == lab]
        dipoles = [d for d in members if d.kind == "dipole"]
        rep = max(dipoles or members, key=lambda d: d.peak_z)
        kind = "dipole" if dipoles else "monopole"
        pm_ra = pm_dec = None
        if dipoles:
            pms = [d.pm for d in dipoles if d.pm is not None]
            if pms:
                pm_ra = float(np.median([p[0] for p in pms]))
                pm_dec = float(np.median([p[1] for p in pms]))
        recurrence = len({(d.det, d.pair) for d in members})
        ctx_ids = sorted({d.ctx for d in members})
        contam = any(_near(diffs[c].contam, rep.x, rep.y, CONTAM_RADIUS_PX) for c in ctx_ids)
        n_good = max(_good_5x5(diffs[c].good, rep.x, rep.y) for c in ctx_ids)
        reasons: list[str] = []
        if contam:
            reasons.append("contamination flags within 3 px in at least one epoch")
        if n_good < MIN_GOOD_PIXELS:
            reasons.append(f"fewer than {MIN_GOOD_PIXELS} good pixels in the 5x5 box ({n_good})")
        if recurrence < 2:
            reasons.append("low-confidence: single detector & pair")
        if kind == "dipole" and pm_ra is not None and math.hypot(pm_ra, pm_dec) > max_pm_mas_yr:
            reasons.append(f"implied motion exceeds {max_pm_mas_yr:.0f} mas/yr (likely subtraction residual)")
        if math.hypot(rep.x - tx, rep.y - ty) <= TARGET_RADIUS_PX:
            reasons.append("at target position (see target evidence)")
        try:
            r, d = grid.wcs.pixel_to_world_values(rep.x, rep.y)
            ra, dec = float(r), float(d)
        except Exception:
            ra, dec = float("nan"), float("nan")
        raws.append(CandidateRaw(
            id="", x=float(rep.x), y=float(rep.y), ra=ra, dec=dec, kind=kind, peak_z=float(max(d.peak_z for d in members)),
            pm_ra=pm_ra, pm_dec=pm_dec, detectors=sorted({d.det for d in members}),
            visit_pairs=sorted({d.pair for d in members}), recurrence=recurrence,
            contamination_near=[CONTAMINATION_LABEL] if contam else [], n_good_pixels=n_good,
            rejection_reasons=reasons))
    raws.sort(key=lambda c: c.peak_z, reverse=True)
    raws = raws[:MAX_CANDIDATES]
    for i, c in enumerate(raws):
        c.id = f"c{i}"
    return raws
