"""Light-curve variability metrics (SCIENCE_REFERENCE §2.5).  ASTRA never fits or claims a period."""
from __future__ import annotations

import math
from typing import Optional

import numpy as np

from .. import models
from .spectrum import BINS_PER_DETECTOR, bin_index

SYSTEMATIC_FLOOR = 0.02      # fraction of flux added in quadrature to every error
OUTLIER_NSIGMA = 5.0
OUTLIER_MIN_POINTS = 5
CHI2_THRESHOLD = 5.0
AMP_THRESHOLD = 5.0
REF_MIN_POINTS = 3


def _err_eff(p: models.PhotPoint) -> Optional[float]:
    if p.flux_ujy is None or p.flux_err_ujy is None or not (p.flux_err_ujy > 0):
        return None
    return math.sqrt(p.flux_err_ujy ** 2 + (SYSTEMATIC_FLOOR * p.flux_ujy) ** 2)


def _usable(p: models.PhotPoint) -> bool:
    """Unsaturated, measured (not rejected), with an error."""
    return (not p.saturated) and p.flux_ujy is not None and math.isfinite(p.flux_ujy) and _err_eff(p) is not None


def _period_note(n_visits: int) -> str:
    return (f"{n_visits} survey visit{'s' if n_visits != 1 else ''} with usable (unsaturated) data. "
            "No period is fitted or claimed: a few visits cannot constrain a period.")


MAX_SHAPE_DEGREE = 2        # polynomial degree of the common in-detector spectral shape (ln F vs λ)


def _fit_offsets(lam: np.ndarray, f: np.ndarray, e: np.ndarray, vidx: np.ndarray, nv: int):
    """Weighted LSQ of ln F = P_deg(λ) + δ_visit (δ_0 = 0) for one detector.

    Every exposure samples a different wavelength, so comparing raw fluxes inside a detector mixes spectral shape
    with time variability. The common shape P absorbs the spectrum; the visit offsets δ carry the variability.
    Returns None when there are too few points for at least one degree of freedom.
    """
    n = len(f)
    deg = min(MAX_SHAPE_DEGREE, n - nv - 1)
    if nv < 2 or deg < 0:
        return None
    a0, a = _design(lam, vidx, nv, deg, lam)
    y = np.log(f)
    sw = f / e                                     # 1/σ_lnF
    try:
        beta, *_ = np.linalg.lstsq(a * sw[:, None], y * sw, rcond=None)
        cov = np.linalg.pinv((a * sw[:, None]).T @ (a * sw[:, None]))
        b0, *_ = np.linalg.lstsq(a0 * sw[:, None], y * sw, rcond=None)
    except np.linalg.LinAlgError:
        return None
    r_full = (y - a @ beta) * sw
    chi2_full = float((r_full ** 2).sum())
    chi2_null = float((((y - a0 @ b0) * sw) ** 2).sum())
    dof_full = n - a.shape[1]
    s2 = max(1.0, chi2_full / dof_full) if dof_full > 0 else 1.0   # inflate errors by any shape misfit
    delta = np.concatenate([[0.0], beta[deg + 1:]])
    dcov = np.zeros((nv, nv))
    dcov[1:, 1:] = cov[deg + 1:, deg + 1:] * s2
    return delta, dcov, r_full, max(0.0, chi2_null - chi2_full) / s2 / (nv - 1), beta, deg, s2


def _design(lam: np.ndarray, vidx: np.ndarray, nv: int, deg: int, ref_lam: np.ndarray):
    """Design matrices (shape-only, shape + visit offsets); λ normalised with the range of ``ref_lam``."""
    span = float(ref_lam.max() - ref_lam.min())
    x = (lam - float(ref_lam.mean())) / (span / 2 if span > 0 else 1.0)
    a0 = np.vstack([x ** k for k in range(deg + 1)]).T
    ind = np.zeros((len(lam), nv - 1))
    for i, v in enumerate(vidx):
        if v > 0:
            ind[i, v - 1] = 1.0
    return a0, np.hstack([a0, ind])


def _loo_outlier(lam, f, e, vidx, nv, j) -> bool:
    """Leave-one-out test: refit without point j and check whether the model predicts it within 5σ."""
    keep = np.arange(len(f)) != j
    if not np.any(vidx[keep] == vidx[j]):
        return False  # its visit would have no other point: an isolated point cannot be told from variability
    # re-index visits so the kept set's visit ids stay contiguous (all visits keep ≥1 point here)
    res = _fit_offsets(lam[keep], f[keep], e[keep], vidx[keep], nv)
    if res is None:
        return False
    beta, deg, s2 = res[4], res[5], res[6]
    _, row = _design(lam[j:j + 1], vidx[j:j + 1], nv, deg, lam[keep])
    pred = float((row @ beta)[0])
    sig = (e[j] / f[j]) * math.sqrt(s2)
    return abs(math.log(f[j]) - pred) > OUTLIER_NSIGMA * sig


def metrics(phot: list[models.PhotPoint], visits: list[models.Visit]) -> tuple[models.LightCurve, list[models.PhotPoint]]:
    """Per-detector variability metrics, outlier flags and rel_flux.

    Within a detector each exposure has its own wavelength, so variability is measured as grey per-visit offsets on
    top of a common smooth spectral shape (``_fit_offsets``), never by comparing raw fluxes at different λ:
      chi2_red   = Δχ² per visit-offset parameter (constant-shape model vs shape + offsets), misfit-scaled; ≈1 if constant
      amp_sigma  = (δ_max − δ_min) / σ(δ_max − δ_min)
      frac_amp   = exp(δ_max − δ_min) − 1
    Returns the LightCurve and a copy of ``phot`` with ``outlier`` and ``rel_flux`` filled.
    """
    out = [p.model_copy() for p in phot]
    for p in out:
        p.outlier = False
        p.rel_flux = None

    visit_mjd = {v.id: v.mjd_mean for v in visits}

    by_det: dict[int, list[int]] = {}
    for i, p in enumerate(out):
        if _usable(p) and p.flux_ujy > 0:
            by_det.setdefault(p.detector, []).append(i)

    mets: list[models.LightCurveMetric] = []
    directions: dict[int, int] = {}
    for det in sorted(by_det):
        idx = list(by_det[det])
        res = None
        max_out = len(idx) // 4
        n_out = 0
        while True:  # fit; test the worst residual leave-one-out; flag and refit (≤ 25% of points)
            vids = sorted({out[i].visit_id for i in idx}, key=lambda v: visit_mjd.get(v, 0.0))
            vpos = {v: k for k, v in enumerate(vids)}
            lam = np.array([out[i].wavelength_um for i in idx], float)
            f = np.array([out[i].flux_ujy for i in idx], float)
            e = np.array([_err_eff(out[i]) for i in idx], float)
            vidx = np.array([vpos[out[i].visit_id] for i in idx])
            res = _fit_offsets(lam, f, e, vidx, len(vids))
            if res is None or len(idx) < OUTLIER_MIN_POINTS or n_out >= max_out:
                break
            j = int(np.argmax(np.abs(res[2])))
            if not _loo_outlier(lam, f, e, vidx, len(vids), j):
                break
            out[idx[j]].outlier = True
            n_out += 1
            idx = [i for k, i in enumerate(idx) if k != j]
        n = len(idx)
        chi2_red = amp_sigma = frac_amp = None
        direction = 0
        if res is not None:
            delta, dcov, chi2_red = res[0], res[1], res[3]
            imax, imin = int(np.argmax(delta)), int(np.argmin(delta))
            var = dcov[imax, imax] + dcov[imin, imin] - 2 * dcov[imax, imin]
            amp_sigma = float((delta[imax] - delta[imin]) / math.sqrt(var)) if var > 0 else None
            frac_amp = float(math.exp(delta[imax] - delta[imin]) - 1.0)
            direction = int(np.sign(delta[-1] - delta[0]))
        directions[det] = direction

        significant = bool(chi2_red is not None and amp_sigma is not None
                           and chi2_red > CHI2_THRESHOLD and amp_sigma > AMP_THRESHOLD)
        mets.append(models.LightCurveMetric(detector=det, n=n, chi2_red=chi2_red, amp_sigma=amp_sigma,
                                            frac_amp=frac_amp, significant=significant))

    sig_dirs = [directions[m.detector] for m in mets if m.significant and directions.get(m.detector, 0) != 0]
    coherent = 0
    if sig_dirs:
        coherent = max(sig_dirs.count(1), sig_dirs.count(-1))

    # ---- reference visit & rel_flux ----
    usable_by_visit: dict[str, list[int]] = {}
    for i, p in enumerate(out):
        if _usable(p) and not p.outlier:
            usable_by_visit.setdefault(p.visit_id, []).append(i)

    def vkey(v: str) -> float:
        return visit_mjd.get(v, float(np.mean([out[i].mjd for i in usable_by_visit[v]])))

    ref_candidates = [v for v, ix in usable_by_visit.items() if len(ix) >= REF_MIN_POINTS]
    reference_visit = min(ref_candidates, key=vkey) if ref_candidates else None
    if reference_visit is not None:
        ref_by_bin: dict[int, list[float]] = {}
        for i in usable_by_visit[reference_visit]:
            k = bin_index(out[i].detector, out[i].wavelength_um)
            if k is not None:
                ref_by_bin.setdefault(k, []).append(out[i].flux_ujy)
        for p in out:
            if p.flux_ujy is None:
                continue
            k = bin_index(p.detector, p.wavelength_um)
            if k is None:
                continue
            vals = ref_by_bin.get(k)
            if not vals:
                # fall back to +-1 channel in the same detector (SCIENCE_REFERENCE §2.5 caveat)
                lo = (k // BINS_PER_DETECTOR) * BINS_PER_DETECTOR
                vals = [x for kk in (k - 1, k + 1) if lo <= kk < lo + BINS_PER_DETECTOR
                        for x in ref_by_bin.get(kk, [])]
            if vals:
                ref = float(np.median(vals))
                if ref > 0:
                    p.rel_flux = float(p.flux_ujy / ref)

    lc = models.LightCurve(metrics=mets, coherent_detectors=coherent, reference_visit=reference_visit,
                           period_note=_period_note(len(usable_by_visit)))
    return lc, out
