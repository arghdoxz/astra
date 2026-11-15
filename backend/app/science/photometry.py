"""Aperture photometry on a NATIVE (not reprojected) cutout (SCIENCE_REFERENCE §2.3).

Conventions
-----------
* ``flux_ujy`` / ``flux_err_ujy`` are *total* fluxes: aperture flux divided by the enclosed fraction
  ``apcorr`` (= f_ap, in (0, 1]).  Exception: saturated measurements are lower limits, so the aperture
  correction is NOT applied to them (dividing a lower limit by f_ap would no longer be a strict bound).
* x, y are 0-based pixel coordinates in the image that was passed in (numpy ``array[y, x]``).
"""
from __future__ import annotations

import math
import warnings
from typing import Optional

import numpy as np
from astropy.stats import sigma_clip
from astropy.wcs.utils import proj_plane_pixel_area, proj_plane_pixel_scales
from photutils.aperture import CircularAperture

from ..core_types import PhotResult

# Flag bits (kept private; flags.py is owned by another module).
_HARD_BITS = (0, 1, 2, 6, 9, 10, 11, 15, 19)
_SAT_BITS = (1, 15)
_CONTAM_BITS = (7, 14, 17, 20, 22, 23, 24, 25, 26, 27, 28)


def _bitmask(bits) -> int:
    m = 0
    for b in bits:
        m |= 1 << b
    return m


_HARD_MASK = _bitmask(_HARD_BITS)
_SAT_MASK = _bitmask(_SAT_BITS)
_NONSAT_HARD_MASK = _HARD_MASK & ~_SAT_MASK

APERTURE_R_FWHM = 1.0
ANNULUS_IN_FWHM = 2.0
ANNULUS_OUT_FWHM = 3.5
MAX_FLAGGED_FRAC = 0.3
MIN_ANNULUS_PIXELS = 10
EPSF_OVERSAMPLING = 5   # EPSF HDU header OVSMPX/OVSMPY = 5 (DATA_SOURCES says x10; the real files say 5)


def pixel_scale_arcsec(wcs) -> float:
    """Mean pixel scale in arcsec of a celestial WCS."""
    return float(np.mean(proj_plane_pixel_scales(wcs))) * 3600.0


def pixel_solid_angle_sr(wcs) -> float:
    """Pixel solid angle in steradians (proj_plane_pixel_area is in deg^2 for a celestial WCS)."""
    return float(proj_plane_pixel_area(wcs)) * (math.pi / 180.0) ** 2


def _exact_weights(shape: tuple[int, int], x: float, y: float, r: float):
    """Exact circle/pixel overlap weights clipped to the image: (slices, weights) or None."""
    ap = CircularAperture((x, y), r)
    m = ap.to_mask(method="exact")
    sl_img, sl_ap = m.get_overlap_slices(shape)
    if sl_img is None:
        return None
    return sl_img, np.asarray(m.data[sl_ap], dtype=float), float(np.sum(m.data))


def _gaussian_apcorr(fwhm_px: float, r_px: float) -> float:
    sigma = fwhm_px / 2.3548200450309493
    return float(1.0 - math.exp(-(r_px ** 2) / (2.0 * sigma ** 2)))


def _epsf_apcorr(epsf: np.ndarray, r_px: float, oversampling: int) -> Optional[float]:
    """Enclosed fraction within r_px native pixels from an oversampled ePSF stamp; None if unusable."""
    try:
        e = np.asarray(epsf, dtype=float)
        if e.ndim != 2 or not np.all(np.isfinite(e)):
            return None
        total = float(e.sum())
        if total <= 0:
            return None
        cy, cx = (e.shape[0] - 1) / 2.0, (e.shape[1] - 1) / 2.0
        w = _exact_weights(e.shape, cx, cy, r_px * oversampling)
        if w is None:
            return None
        sl, wt, _ = w
        f = float((e[sl] * wt).sum()) / total
        if not (0.05 < f <= 1.2):
            return None
        return min(f, 1.0)
    except Exception:
        return None


def background_annulus(image: np.ndarray, valid: np.ndarray, x: float, y: float,
                r_in: float, r_out: float) -> Optional[tuple[float, float, int]]:
    """Sigma-clipped (median, std, n_kept) of valid annulus pixels, or None if too few."""
    yy, xx = np.indices(image.shape)
    d = np.hypot(xx - x, yy - y)
    sel = (d >= r_in) & (d < r_out) & valid
    if int(sel.sum()) < MIN_ANNULUS_PIXELS:
        return None
    vals = image[sel].astype(float)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        sc = sigma_clip(vals, sigma=3.0, maxiters=5, masked=True)
    kept = np.asarray(sc.compressed(), dtype=float)
    if kept.size < MIN_ANNULUS_PIXELS // 2:
        return None
    return float(np.median(kept)), float(np.std(kept, ddof=1)), int(kept.size)


def _core(image: np.ndarray, variance: np.ndarray, valid: np.ndarray, x: float, y: float, r_px: float):
    """Background-subtracted aperture sum in image units (MJy/sr summed over pixels).

    Returns dict(net, var, n_ap, bkg, sig_bkg, n_ann, sl, wt) or None when it cannot be measured.
    ``var`` = Σ_ap V + N_ap² σ_bkg² / N_ann  (image units squared, before the (1e12 Ω)² factor).
    """
    w = _exact_weights(image.shape, x, y, r_px)
    if w is None:
        return None
    bk = background_annulus(image, valid, x, y, ANNULUS_IN_FWHM * r_px / APERTURE_R_FWHM,
                     ANNULUS_OUT_FWHM * r_px / APERTURE_R_FWHM)
    if bk is None:
        return None
    bkg, sig_bkg, n_ann = bk
    sl, wt, _ = w
    v = valid[sl]
    wv = wt * v
    n_ap = float(wv.sum())
    if n_ap <= 0:
        return None
    s = float(np.sum(np.where(v, image[sl], 0.0) * wt))
    sv = float(np.sum(np.where(v, variance[sl], 0.0) * wt))
    net = s - n_ap * bkg
    var = sv + (n_ap ** 2) * (sig_bkg ** 2) / n_ann
    return dict(net=net, var=var, n_ap=n_ap, bkg=bkg, sig_bkg=sig_bkg, n_ann=n_ann, sl=sl, wt=wt)


def _reject(x: float, y: float, saturated: bool = False, flagged: float = 1.0,
            contam: Optional[list[str]] = None, apcorr: float = 1.0, method: str = "gaussian") -> PhotResult:
    return PhotResult(flux_ujy=None, flux_err_ujy=None, snr=None, ab_mag=None, saturated=saturated,
                      flagged_frac=float(flagged), contamination_bits=contam or [], apcorr=float(apcorr),
                      apcorr_method=method, x=float(x), y=float(y), rejected=not saturated)


def measure(image: np.ndarray, variance: np.ndarray, raw_flags: np.ndarray, hard_mask: np.ndarray, wcs,
            ra: float, dec: float, fwhm_arcsec: float, flag_names: dict[int, str],
            epsf: Optional[np.ndarray] = None, epsf_oversampling: int = EPSF_OVERSAMPLING) -> PhotResult:
    """Aperture photometry of (ra, dec) on one native cutout.  Never raises for bad geometry/data."""
    image = np.asarray(image, dtype=float)
    variance = np.asarray(variance, dtype=float)
    raw = np.asarray(raw_flags).astype(np.int64)
    hard = np.asarray(hard_mask, dtype=bool)
    ny, nx = image.shape

    try:
        px, py = wcs.all_world2pix(float(ra), float(dec), 0)
        x, y = float(px), float(py)
    except Exception:
        return _reject(float("nan"), float("nan"))
    if not (math.isfinite(x) and math.isfinite(y)) or x < -0.5 or y < -0.5 or x > nx - 0.5 or y > ny - 0.5:
        return _reject(x, y)

    pixscale = pixel_scale_arcsec(wcs)
    omega = pixel_solid_angle_sr(wcs)
    fwhm_px = float(fwhm_arcsec) / pixscale
    if not math.isfinite(fwhm_px) or fwhm_px <= 0:
        return _reject(x, y)
    r_px = APERTURE_R_FWHM * fwhm_px

    sat_pix = (raw & _SAT_MASK) != 0
    nonsat_hard_pix = (raw & _NONSAT_HARD_MASK) != 0
    valid = np.isfinite(image) & np.isfinite(variance) & (variance > 0) & ~hard

    yy, xx = np.indices(image.shape)
    dist = np.hypot(xx - x, yy - y)

    # --- contamination near aperture (+1 px), saturation, flagged fraction -------------------------------
    near = dist <= r_px + 1.0
    contam: list[str] = []
    for b in _CONTAM_BITS:
        if np.any(near & ((raw >> b) & 1).astype(bool)):
            contam.append(flag_names.get(b, f"BIT{b}"))

    w = _exact_weights(image.shape, x, y, r_px)
    if w is None:
        return _reject(x, y, contam=contam)
    sl, wt, area = w
    saturated = bool(np.any(sat_pix[sl] & (wt > 0)))
    sat_only = sat_pix[sl] & ~nonsat_hard_pix[sl]
    w_valid = float((wt * valid[sl]).sum())
    w_sat = float((wt * (sat_only & ~valid[sl])).sum())
    denom = area - w_sat
    flagged_frac = 1.0 if denom <= 0 else float(np.clip((area - w_valid - w_sat) / denom, 0.0, 1.0))
    if flagged_frac < 1e-9:
        flagged_frac = 0.0

    # --- aperture correction ---------------------------------------------------------------------------
    f_ap = _epsf_apcorr(epsf, r_px, epsf_oversampling) if epsf is not None else None
    if f_ap is not None:
        method = "epsf"
    else:
        f_ap, method = _gaussian_apcorr(fwhm_px, r_px), "gaussian"

    if flagged_frac > MAX_FLAGGED_FRAC and not saturated:
        return _reject(x, y, False, flagged_frac, contam, f_ap, method)

    core = _core(image, variance, valid, x, y, r_px)
    if core is None:
        return _reject(x, y, saturated, flagged_frac, contam, f_ap, method)  # rejected only if not saturated

    scale = 1e12 * omega                      # MJy/sr summed over pixels -> µJy
    flux = core["net"] * scale
    err = math.sqrt(max(core["var"], 0.0)) * scale
    if not saturated:
        flux /= f_ap
        err /= f_ap
    snr = flux / err if err > 0 else None
    ab = 23.9 - 2.5 * math.log10(flux) if flux > 0 else None
    return PhotResult(flux_ujy=float(flux), flux_err_ujy=float(err),
                      snr=None if snr is None else float(snr), ab_mag=None if ab is None else float(ab),
                      saturated=saturated, flagged_frac=flagged_frac, contamination_bits=contam,
                      apcorr=float(f_ap), apcorr_method=method, x=x, y=y, rejected=False)


def forced_snr_on_stack(S: np.ndarray, V: np.ndarray, grid_wcs, ra: float, dec: float,
                        fwhm_px: float) -> Optional[float]:
    """Aperture S/N of (ra, dec) on a stack (r = 1 FWHM, annulus 2-3.5 FWHM); None if unmeasurable.

    Uses the same σ² model as :func:`measure`; the pixel solid angle cancels so this is unit-free.
    No aperture correction is applied (this is a detection statistic).
    """
    try:
        S = np.asarray(S, dtype=float)
        V = np.asarray(V, dtype=float)
        px, py = grid_wcs.all_world2pix(float(ra), float(dec), 0)
        x, y = float(px), float(py)
        ny, nx = S.shape
        if not (math.isfinite(x) and math.isfinite(y)) or x < -0.5 or y < -0.5 or x > nx - 0.5 or y > ny - 0.5:
            return None
        if not math.isfinite(fwhm_px) or fwhm_px <= 0:
            return None
        valid = np.isfinite(S) & np.isfinite(V) & (V > 0)
        core = _core(S, V, valid, x, y, float(fwhm_px))
        if core is None or core["var"] <= 0:
            return None
        return float(core["net"] / math.sqrt(core["var"]))
    except Exception:
        return None
