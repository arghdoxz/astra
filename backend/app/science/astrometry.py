"""Centroids, proper-motion fit, residuals and registration check (SCIENCE_REFERENCE §2.6)."""
from __future__ import annotations

import math
import warnings
from typing import Optional

import numpy as np
from scipy.ndimage import maximum_filter

from .. import models
from ..core_types import CentroidResult
from . import ephemeris
from .photometry import background_annulus, pixel_scale_arcsec

SYS_FLOOR_ARCSEC = 0.3
MIN_SNR_CENTROID = 5.0
MIN_SNR_FIT = 10.0
MAX_NAN_FRAC = 0.2
CROWD_FRACTION = 0.2
MIN_BASELINE_PM_YR = 0.25
MIN_BASELINE_PARALLAX_YR = 1.0
MIN_EPOCHS_PARALLAX = 4
_FWHM_TO_SIGMA = 2.355


# --------------------------------------------------------------------------- centroid
def centroid(image: np.ndarray, variance: np.ndarray, wcs, ra_guess: float, dec_guess: float,
             fwhm_px: float) -> Optional[CentroidResult]:
    """2-D Gaussian centroid in a 5x5 (7x7 if fwhm_px > 2.5) box around the guess.

    Returns None when the box is off-image, >20% NaN, the aperture SNR < 5, or the fit fails.
    ``saturated`` is left False: this function has no access to raw flags (caller sets it).
    """
    from photutils.centroids import centroid_2dg, centroid_com

    img = np.asarray(image, dtype=float)
    var = np.asarray(variance, dtype=float)
    ny, nx = img.shape
    try:
        gx, gy = wcs.all_world2pix(float(ra_guess), float(dec_guess), 0)
        gx, gy = float(gx), float(gy)
    except Exception:
        return None
    if not (math.isfinite(gx) and math.isfinite(gy)):
        return None
    half = 3 if fwhm_px > 2.5 else 2
    x0, y0 = int(round(gx)), int(round(gy))
    xs, xe, ys, ye = x0 - half, x0 + half + 1, y0 - half, y0 + half + 1
    if xs < 0 or ys < 0 or xe > nx or ye > ny:
        return None
    box = img[ys:ye, xs:xe].copy()
    finite = np.isfinite(box)
    if (1.0 - finite.mean()) > MAX_NAN_FRAC or finite.sum() < 6:
        return None

    # peak pixel of the raw box, then a local residual background from an annulus outside the box
    # (2-3.5 FWHM around the peak); the image is already median-subtracted so 0 is the fallback.
    pk = np.unravel_index(int(np.nanargmax(np.where(finite, box, -np.inf))), box.shape)
    px_pk, py_pk = xs + pk[1], ys + pk[0]
    valid_img = np.isfinite(img) & np.isfinite(var) & (var > 0)
    ann = background_annulus(img, valid_img, float(px_pk), float(py_pk), 2.0 * fwhm_px, 3.5 * fwhm_px)
    bkg = ann[0] if ann is not None else 0.0
    bs = box - bkg
    bs_f = np.where(finite, bs, np.nan)
    peak_val = float(bs_f[pk])
    if not peak_val > 0:
        return None

    # SNR: background-subtracted aperture sum / sqrt(sum of variance), aperture on the peak pixel
    r_ap = max(float(fwhm_px), 1.0)
    yy, xx = np.indices(img.shape)
    inap = np.hypot(xx - px_pk, yy - py_pk) <= r_ap
    good = inap & np.isfinite(img) & np.isfinite(var) & (var > 0)
    if good.sum() < 3:
        return None
    snr = float((img[good] - bkg).sum() / math.sqrt(var[good].sum()))
    if not math.isfinite(snr) or snr < MIN_SNR_CENTROID:
        return None

    # centroid: 2-D Gaussian fit, fall back to centre of mass if it fails or wanders off
    cx = cy = None
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            cx, cy = centroid_2dg(np.where(finite, bs, 0.0), mask=~finite)
        if not (math.isfinite(cx) and math.isfinite(cy)) or math.hypot(cx - pk[1], cy - pk[0]) > 2.0:
            cx = None
    except Exception:
        cx = None
    if cx is None:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                pos = np.where(finite & (bs > 0), bs, 0.0)
                cx, cy = centroid_com(pos)
        except Exception:
            return None
        if not (math.isfinite(cx) and math.isfinite(cy)):
            return None
    x, y = xs + float(cx), ys + float(cy)
    try:
        ra, dec = wcs.all_pix2world(x, y, 0)
    except Exception:
        return None

    pixscale = pixel_scale_arcsec(wcs)
    fwhm_arcsec = fwhm_px * pixscale
    err = math.sqrt((fwhm_arcsec / (_FWHM_TO_SIGMA * snr)) ** 2 + SYS_FLOOR_ARCSEC ** 2)

    # crowding: another local maximum > 20% of the peak within 2 FWHM of the target peak
    work = np.where(np.isfinite(img), img - bkg, -np.inf)
    lm = (maximum_filter(work, size=3, mode="constant", cval=-np.inf) == work) & (work > CROWD_FRACTION * peak_val)
    d_pk = np.hypot(xx - px_pk, yy - py_pk)
    others = lm & (d_pk <= 2.0 * fwhm_px) & ~((xx == px_pk) & (yy == py_pk))
    crowded = bool(others.any())

    return CentroidResult(ra=float(ra), dec=float(dec), x=x, y=y, err_arcsec=float(err), snr=snr,
                          crowded=crowded, saturated=False)


# --------------------------------------------------------------------------- residuals
def _pred_arrays(measured: list[models.AstrometryMeasured], target: models.Target):
    pred = ephemeris.predict_track(target, [m.mjd for m in measured])
    return np.array([p[0] for p in pred]), np.array([p[1] for p in pred])


def residuals(measured: list[models.AstrometryMeasured], target: models.Target) -> list[models.AstrometryMeasured]:
    """Fill resid_ra_arcsec (ΔRA·cosδ) and resid_dec_arcsec = observed - predicted track."""
    if not measured:
        return []
    pra, pdec = _pred_arrays(measured, target)
    out = []
    for m, a, d in zip(measured, pra, pdec):
        dra = ((m.ra - a + 180.0) % 360.0) - 180.0
        out.append(m.model_copy(update={
            "resid_ra_arcsec": float(dra * math.cos(math.radians(d)) * 3600.0),
            "resid_dec_arcsec": float((m.dec - d) * 3600.0)}))
    return out


# --------------------------------------------------------------------------- PM fit
def fit_pm(measured: list[models.AstrometryMeasured], target: models.Target) -> Optional[models.AstrometryFit]:
    """Weighted linear fit of position vs time (units: mas, mas/yr).

    Uses non-crowded, non-saturated points with SNR >= 10.  Needs >= 2 points with baseline >= 0.25 yr.
    Catalog parallax (if any) is subtracted first.  With >= 4 distinct visits and baseline >= 1 yr the
    parallax is also fitted jointly (shared by both axes) and parallax_mode is "fitted".
    Uncertainties come from the covariance scaled by sqrt(max(chi2_red, 1)).
    """
    use = [m for m in measured if not m.crowded and not m.saturated and m.snr >= MIN_SNR_FIT and m.err_arcsec > 0]
    if len(use) < 2:
        return None
    mjd = np.array([m.mjd for m in use], dtype=float)
    baseline_yr = float((mjd.max() - mjd.min()) / 365.25)
    if baseline_yr < MIN_BASELINE_PM_YR:
        return None

    ra = np.array([m.ra for m in use], dtype=float)
    dec = np.array([m.dec for m in use], dtype=float)
    ra0 = float(np.angle(np.mean(np.exp(1j * np.radians(ra))), deg=True) % 360.0)
    dec0 = float(np.mean(dec))
    cosd = math.cos(math.radians(dec0))
    x = ((ra - ra0 + 180.0) % 360.0 - 180.0) * cosd * 3.6e6      # mas
    y = (dec - dec0) * 3.6e6
    sig = np.array([m.err_arcsec for m in use], dtype=float) * 1000.0   # mas
    dt = (mjd - mjd.mean()) / 365.25
    n = len(use)

    P = ephemeris.parallax_factors(ra0, dec0, mjd)               # (n, 2), mas per mas
    n_visits = len({m.visit_id for m in use})
    fit_parallax = n_visits >= MIN_EPOCHS_PARALLAX and baseline_yr >= MIN_BASELINE_PARALLAX_YR

    cat_plx = target.parallax if (target.parallax is not None and target.parallax > 0) else None

    if fit_parallax:
        A = np.zeros((2 * n, 5))
        A[:n, 0], A[:n, 1], A[:n, 4] = dt, 1.0, P[:, 0]
        A[n:, 2], A[n:, 3], A[n:, 4] = dt, 1.0, P[:, 1]
        b = np.concatenate([x, y])
        s = np.concatenate([sig, sig])
        mode = "fitted"
    else:
        xs_, ys_ = x.copy(), y.copy()
        if cat_plx is not None:
            xs_ = xs_ - cat_plx * P[:, 0]
            ys_ = ys_ - cat_plx * P[:, 1]
        A = np.zeros((2 * n, 4))
        A[:n, 0], A[:n, 1] = dt, 1.0
        A[n:, 2], A[n:, 3] = dt, 1.0
        b = np.concatenate([xs_, ys_])
        s = np.concatenate([sig, sig])
        mode = "fixed_catalog" if cat_plx is not None else "none"

    Aw = A / s[:, None]
    bw = b / s
    try:
        cov = np.linalg.inv(Aw.T @ Aw)
    except np.linalg.LinAlgError:
        return None
    theta = cov @ (Aw.T @ bw)
    chi2 = float(np.sum((bw - Aw @ theta) ** 2))
    dof = 2 * n - A.shape[1]
    chi2_red = chi2 / dof if dof > 0 else 0.0     # no degrees of freedom -> cannot assess; errors unscaled
    cov = cov * max(chi2_red, 1.0)
    err = np.sqrt(np.diag(cov))

    plx = plx_err = None
    if mode == "fitted":
        plx, plx_err = float(theta[4]), float(err[4])
    elif mode == "fixed_catalog":
        plx = float(cat_plx)
    return models.AstrometryFit(
        pm_ra=float(theta[0]), pm_dec=float(theta[2]), pm_ra_err=float(err[0]), pm_dec_err=float(err[2]),
        chi2_red=float(chi2_red), baseline_yr=baseline_yr, parallax_mode=mode,
        parallax=plx, parallax_err=plx_err, n_points=n)


# --------------------------------------------------------------------------- registration
def registration_check(image: np.ndarray, wcs, gaia_stars: list[models.CatalogMatch], fwhm_px: float,
                       variance: Optional[np.ndarray] = None) -> Optional[models.Registration]:
    """Centroid each (epoch-propagated) Gaia star and report offsets of measured - catalog.

    Keeps SNR >= 10 non-saturated stars (saturated = centroid.saturated; this routine only sees NaN-masked
    pixels, so stars with a masked core fail the NaN/SNR cuts).  Returns None if fewer than 3 stars survive.
    ``variance`` is optional; when omitted the variance is estimated from the image robust scatter.
    """
    img = np.asarray(image, dtype=float)
    if variance is None:
        fin = img[np.isfinite(img)]
        if fin.size < 10:
            return None
        mad = 1.4826 * float(np.median(np.abs(fin - np.median(fin))))
        var = np.full(img.shape, max(mad, 1e-12) ** 2)
    else:
        var = np.asarray(variance, dtype=float)
    offs = []
    for s in gaia_stars:
        c = centroid(img, var, wcs, s.ra, s.dec, fwhm_px)
        if c is None or c.saturated or c.snr < MIN_SNR_FIT:
            continue
        dra = ((c.ra - s.ra + 180.0) % 360.0) - 180.0
        dx = dra * math.cos(math.radians(s.dec)) * 3600.0
        dy = (c.dec - s.dec) * 3600.0
        offs.append((dx, dy))
    if len(offs) < 3:
        return None
    o = np.array(offs)
    mag = np.hypot(o[:, 0], o[:, 1])
    # median offset: magnitude of the median vector (systematic shift), rms: of the individual offsets
    med = float(np.hypot(np.median(o[:, 0]), np.median(o[:, 1])))
    rms = float(np.sqrt(np.mean(mag ** 2)))
    return models.Registration(n_stars=len(offs), median_offset_arcsec=med, rms_arcsec=rms)
