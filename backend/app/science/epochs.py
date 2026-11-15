"""Common-grid construction, reprojection and inverse-variance stacking (SCIENCE_REFERENCE §2.2).

Pixel convention (API_CONTRACT): arrays are ``[y, x]``, y increases north, x increases west (east is left).
"""
from __future__ import annotations

import math
import warnings

import numpy as np
from astropy.wcs import WCS
from reproject import reproject_interp

from ..core_types import CutoutData, GridSpec, Stack
from . import flags as F


def make_grid(ra: float, dec: float, fov_arcmin: float, pixscale_arcsec: float = 6.15) -> GridSpec:
    """North-up TAN grid centred on (ra, dec).

    Size n = ceil(fov*60/pixscale) rounded up to odd; the target sits exactly on the centre pixel
    (1-based CRPIX = (n+1)/2, i.e. 0-based pixel (n-1)/2). CDELT1 < 0 so east is left.
    """
    n = int(math.ceil(fov_arcmin * 60.0 / pixscale_arcsec - 1e-9))
    n = max(n, 3)
    if n % 2 == 0:
        n += 1
    w = WCS(naxis=2)
    w.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    w.wcs.crval = [float(ra), float(dec)]
    w.wcs.crpix = [(n + 1) / 2.0, (n + 1) / 2.0]
    step = pixscale_arcsec / 3600.0
    w.wcs.cdelt = [-step, step]
    w.wcs.cunit = ["deg", "deg"]
    w.array_shape = (n, n)
    return GridSpec(wcs=w, shape=(n, n), ra=float(ra), dec=float(dec), pixscale_arcsec=float(pixscale_arcsec))


def _interp(arr: np.ndarray, wcs: WCS, grid: GridSpec, order: str):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        out, fp = reproject_interp((np.asarray(arr, dtype=np.float64), wcs), grid.wcs,
                                   shape_out=grid.shape, order=order)
    return out, fp


def reproject_cutout(cut: CutoutData, grid: GridSpec) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Bilinear-reproject image and variance onto ``grid``.

    Returns (I, V, mask) as float32, float32, bool; mask=True where either is NaN or outside the footprint.
    Variance is reprojected the same way as the image (correlates neighbours; documented limitation).
    """
    img, fp_i = _interp(cut.image, cut.wcs, grid, "bilinear")
    var, fp_v = _interp(cut.variance, cut.wcs, grid, "bilinear")
    mask = ~np.isfinite(img) | ~np.isfinite(var) | (fp_i == 0) | (fp_v == 0)
    img = np.where(mask, np.nan, img).astype(np.float32)
    var = np.where(mask, np.nan, var).astype(np.float32)
    return img, var, mask


def _reproject_bool(m: np.ndarray, wcs: WCS, grid: GridSpec) -> np.ndarray:
    out, _ = _interp(np.asarray(m, dtype=np.float64), wcs, grid, "nearest-neighbor")
    return np.nan_to_num(out, nan=0.0) > 0.5


def reproject_flags(cut: CutoutData, grid: GridSpec) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Nearest-neighbour reprojection of bit masks onto ``grid`` -> (hard, contamination, saturation), all bool.

    Outside the cutout footprint all three are False.
    """
    hard = _reproject_bool(F.hard_mask(cut.raw_flags) | np.asarray(cut.hard, dtype=bool), cut.wcs, grid)
    contam = _reproject_bool(F.contamination_mask(cut.raw_flags), cut.wcs, grid)
    sat = _reproject_bool(F.saturation_mask(cut.raw_flags), cut.wcs, grid)
    return hard, contam, sat


def stack(images, variances, masks) -> Stack:
    """Inverse-variance weighted mean of reprojected frames.

    S = sum(I/V) / sum(1/V); V_S = 1 / sum(1/V); NaN, masked and V<=0 samples are ignored.
    ``n`` counts contributing frames per pixel; ``mask`` is True where n == 0 (S, V are NaN there).
    """
    images = [np.asarray(a) for a in images]
    variances = [np.asarray(a) for a in variances]
    masks = [np.asarray(a, dtype=bool) for a in masks]
    if not images:
        raise ValueError("stack() needs at least one frame")
    if not (len(images) == len(variances) == len(masks)):
        raise ValueError("images, variances and masks must have the same length")
    shape = images[0].shape
    sw = np.zeros(shape, dtype=np.float64)    # sum of weights
    swi = np.zeros(shape, dtype=np.float64)   # sum of weight*image
    n = np.zeros(shape, dtype=np.int32)
    for im, v, m in zip(images, variances, masks):
        if im.shape != shape or v.shape != shape or m.shape != shape:
            raise ValueError("all frames must share one shape")
        im = im.astype(np.float64, copy=False)
        v = v.astype(np.float64, copy=False)
        ok = ~m & np.isfinite(im) & np.isfinite(v) & (v > 0)
        w = np.zeros(shape, dtype=np.float64)
        w[ok] = 1.0 / v[ok]
        sw += w
        swi += np.where(ok, im, 0.0) * w
        n += ok.astype(np.int32)
    empty = n == 0
    with np.errstate(divide="ignore", invalid="ignore"):
        S = np.where(empty, np.nan, swi / sw)
        V = np.where(empty, np.nan, 1.0 / sw)
    return Stack(S=S.astype(np.float32), V=V.astype(np.float32), n=n, mask=empty)


def stack_cutouts(cuts: list[CutoutData], grid: GridSpec) -> Stack:
    """Reproject every cutout onto ``grid`` and stack.

    Contamination is OR-ed across members (nearest-neighbour reprojected); fwhm_arcsec = median header
    PSF_FWHM; obs_ids preserved in input order. Across detectors this is the "all-IR" stack
    (display / detection only, never photometry).
    """
    if not cuts:
        raise ValueError("stack_cutouts() needs at least one cutout")
    ims, vs, ms = [], [], []
    contam = np.zeros(grid.shape, dtype=bool)
    for c in cuts:
        i, v, m = reproject_cutout(c, grid)
        ims.append(i)
        vs.append(v)
        ms.append(m)
        contam |= _reproject_bool(F.contamination_mask(c.raw_flags), c.wcs, grid)
    st = stack(ims, vs, ms)
    st.contam = contam
    fw = [float(c.psf_fwhm_arcsec) for c in cuts if c.psf_fwhm_arcsec is not None and np.isfinite(c.psf_fwhm_arcsec)]
    st.fwhm_arcsec = float(np.median(fw)) if fw else None
    st.obs_ids = [c.obs_id for c in cuts]
    return st
