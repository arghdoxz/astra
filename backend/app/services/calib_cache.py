"""Per-(detector, pipeline VERSION) calibration cache: the EPSF table and the WCS-WAVE lookup table.

Streaming cutouts stop before the EPSF HDU, so they carry neither ``EPSF`` nor ``WCS-WAVE``. Both are properties
of the detector calibration, not of the exposure, so one full small cutout per (detector, VERSION) is downloaded
once and its ``EPSF`` + ``WCS-WAVE`` HDUs are stored in ``cache/calib/D{det}_{version}.fits``.

Wavelength (verified on the real DR1 fixture): the IMAGE header holds the alternate WCS ``W`` (``CTYPE*W =
WAVE-TAB``; ``PV1_3W=1`` -> VALUES[...,0] is the central wavelength, ``PV2_3W=2`` -> VALUES[...,1] is the
bandwidth; table in extension ``WCS-WAVE`` with control points X, Y = 1..2040; ``CRPIX*W`` already carries the
cutout offset). ``WCS(header, fobj=hdul, key="W")`` evaluated at a pixel returns (lambda_um, bandwidth_um).
"""
from __future__ import annotations

import asyncio
import io
import logging
import re
import warnings
from pathlib import Path
from typing import Optional

import numpy as np
from astropy.io import fits
from astropy.wcs import WCS

from .. import models
from ..core_types import CutoutData
from . import cache
from .cutouts import download_full
from .irsa_sia import DETECTOR_BANDS

log = logging.getLogger("astra.calib")

CALIB_CUTOUT_DEG = 0.01
# Nominal resolving power per detector (SCIENCE_REFERENCE section 1) - only used to estimate a bandwidth when the
# table does not carry one.
_DETECTOR_R = {1: 39.0, 2: 41.0, 3: 41.0, 4: 35.0, 5: 112.0, 6: 128.0}

_locks: dict[tuple[int, str], asyncio.Lock] = {}
_wave_tables: dict[tuple[str, int], fits.BinTableHDU] = {}
_epsf_tables: dict[tuple[str, int], dict] = {}


def _strip_sip(header: fits.Header) -> fits.Header:
    """Copy of ``header`` without SIP polynomial cards (they only belong to the celestial WCS; astropy would
    otherwise apply them to the alternate 'A'/'W' WCS as well)."""
    h = header.copy()
    for k in [k for k in h if re.match(r"^(A|B|AP|BP)_(\d+_\d+|ORDER)$", str(k))]:
        del h[k]
    return h


def calib_file(detector: int, version: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", str(version))
    return cache.cache_path("calib", f"D{int(detector)}_{safe}", "fits")


def _lock_for(key: str) -> asyncio.Lock:
    lk = (id(asyncio.get_running_loop()), key)
    lock = _locks.get(lk)
    if lock is None:
        for stale in [k for k in _locks if k[0] != lk[0]]:
            del _locks[stale]
        lock = _locks[lk] = asyncio.Lock()
    return lock


def _build_calib_bytes(raw: bytes) -> bytes:
    """Extract EPSF + WCS-WAVE (plus a header-only IMAGE for reference) from a full cutout response."""
    with fits.open(io.BytesIO(raw), memmap=False) as src:
        names = {h.name.upper() for h in src}
        if "EPSF" not in names or "WCS-WAVE" not in names:
            raise ValueError("full cutout lacks EPSF or WCS-WAVE")
        prim = fits.PrimaryHDU()
        for key in ("VERSION",):
            if key in src[0].header:
                prim.header[key] = src[0].header[key]
        img_hdr = src["IMAGE"].header
        for key in ("DETECTOR", "OBSID"):
            if key in img_hdr:
                prim.header[key] = img_hdr[key]
        prim.header["COMMENT"] = "ASTRA calibration cache: EPSF + WCS-WAVE from one full SPHEREx cutout"
        ref = fits.ImageHDU(header=img_hdr.copy(), name="IMAGE")  # header-only reference
        epsf = fits.BinTableHDU(data=src["EPSF"].data.copy(), header=src["EPSF"].header.copy(), name="EPSF")
        wave = fits.BinTableHDU(data=src["WCS-WAVE"].data.copy(), header=src["WCS-WAVE"].header.copy(),
                                name="WCS-WAVE")
        out = io.BytesIO()
        fits.HDUList([prim, ref, epsf, wave]).writeto(out)
        return out.getvalue()


async def ensure_calib(
    detector: int, version: str, sample: models.Exposure, ra: float, dec: float
) -> Path | None:
    """Make sure the calibration file for (detector, version) exists; returns its path or None on failure.

    Downloads one FULL 0.01 deg cutout of ``sample`` (centred on ra/dec) the first time. Concurrent callers for the
    same key share one download (asyncio.Lock per key).
    """
    path = calib_file(detector, version)
    if path.exists() and path.stat().st_size > 0:
        return path
    async with _lock_for(path.name):
        if path.exists() and path.stat().st_size > 0:
            return path
        try:
            raw = await download_full(sample, ra, dec, CALIB_CUTOUT_DEG)
            data = await asyncio.to_thread(_build_calib_bytes, raw)
            cache.atomic_write_bytes(path, data)
            return path
        except Exception as e:
            log.warning("calibration fetch failed for D%s %s: %s", detector, version, type(e).__name__)
            return None


# ------------------------------------------------------------------------------------------------ wavelength
def _wave_table(calib_path: Path) -> fits.BinTableHDU:
    key = (str(calib_path), calib_path.stat().st_mtime_ns)
    tab = _wave_tables.get(key)
    if tab is None:
        with fits.open(calib_path, memmap=False) as h:
            src = h["WCS-WAVE"]
            tab = fits.BinTableHDU(data=src.data.copy(), header=src.header.copy(), name="WCS-WAVE")
        _wave_tables[key] = tab
    return tab


def _fallback_band(cut: CutoutData, exp: Optional[models.Exposure]) -> tuple[float, float, str]:
    if exp is not None:
        lo, hi = exp.em_min_um, exp.em_max_um
    else:  # nominal detector coverage
        lo, hi = DETECTOR_BANDS.get(cut.detector, (float("nan"), float("nan")))
    lam = 0.5 * (lo + hi)
    return float(lam), float(lam / _DETECTOR_R.get(cut.detector, 40.0)), "sia_band_center"


def wavelength_at(
    cut: CutoutData, ra: float, dec: float, calib_path: Path | None, *, exp: Optional[models.Exposure] = None
) -> tuple[float, float, str]:
    """(lambda_um, bandwidth_um, source) at the pixel of (ra, dec).

    source "wcs_wave": cached WCS-WAVE table + the cutout's own ``CRPIX*W`` (bandwidth read from the table's second
    value). source "sia_band_center": fallback = midpoint of the exposure's SIA ``em_min``/``em_max`` (or the
    detector's nominal band when ``exp`` is omitted), bandwidth = lambda / R_nominal.
    """
    if calib_path is not None and Path(calib_path).exists():
        try:
            tab = _wave_table(Path(calib_path))
            hdul = fits.HDUList([fits.PrimaryHDU(), tab])
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                w = WCS(_strip_sip(cut.header), fobj=hdul, key="W")
                ny, nx = cut.image.shape
                xy = cut.wcs.all_world2pix([[ra, dec]], 0)[0]
                x = float(np.clip(xy[0], 0, nx - 1))
                y = float(np.clip(xy[1], 0, ny - 1))
                lam, bw = (float(v) for v in w.all_pix2world([[x, y]], 0)[0])
            if lam < 0.01:  # wcslib normalised to metres
                lam, bw = lam * 1e6, bw * 1e6
            lo, hi = DETECTOR_BANDS.get(cut.detector, (0.6, 5.2))
            if np.isfinite(lam) and np.isfinite(bw) and bw > 0 and 0.9 * lo <= lam <= 1.1 * hi:
                return lam, bw, "wcs_wave"
            log.warning("WCS-WAVE value out of range for D%s: %s", cut.detector, lam)
        except Exception as e:
            log.warning("WCS-WAVE evaluation failed: %s", type(e).__name__)
    return _fallback_band(cut, exp)


def detector_xy(cut: CutoutData, x: float, y: float) -> tuple[float, float]:
    """Cutout pixel (0-based) -> detector pixel (0-based active-pixel coordinates, WCS key 'A'), as used by the
    EPSF zone centres. Falls back to the raw CRPIX*A offset."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            wa = WCS(_strip_sip(cut.header), key="A")
            xd, yd = wa.all_pix2world([[x, y]], 0)[0]
        return float(xd), float(yd)
    except Exception:
        h = cut.header
        return float(x + 1 - h.get("CRPIX1A", 0.0)), float(y + 1 - h.get("CRPIX2A", 0.0))


# ------------------------------------------------------------------------------------------------ ePSF
def _epsf_table(calib_path: Path) -> dict:
    key = (str(calib_path), calib_path.stat().st_mtime_ns)
    t = _epsf_tables.get(key)
    if t is None:
        with fits.open(calib_path, memmap=False) as h:
            d = h["EPSF"].data
            hdr = h["EPSF"].header
            epsf = np.array(d["EPSF"], dtype=np.float64)
            if epsf.ndim == 2:  # no TDIM: reshape square
                n = int(round(np.sqrt(epsf.shape[1])))
                epsf = epsf.reshape(-1, n, n)
            sums = np.nansum(epsf, axis=(1, 2))
            t = {
                "xc": np.array(d["XCENTER"], dtype=float), "yc": np.array(d["YCENTER"], dtype=float),
                "xw": np.array(d["XWIDTH"], dtype=float), "yw": np.array(d["YWIDTH"], dtype=float),
                "epsf": epsf, "sums": sums, "oversample": int(hdr.get("OVSMPX", 1)),
            }
        _epsf_tables[key] = t
    return t


def epsf_oversampling(calib_path: Path | None) -> int | None:
    """Oversampling factor of the stored ePSF (header ``OVSMPX``; 5 in DR1 D6), or None."""
    if calib_path is None or not Path(calib_path).exists():
        return None
    try:
        return int(_epsf_table(Path(calib_path))["oversample"])
    except Exception:
        return None


def load_epsf(calib_path: Path | None, x_det: float, y_det: float) -> np.ndarray | None:
    """Oversampled ePSF (2-D, sum = 1) of the zone nearest to detector pixel (x_det, y_det) (0-based active-pixel
    coordinates, see ``detector_xy``). Returns None if unavailable."""
    if calib_path is None or not Path(calib_path).exists():
        return None
    try:
        t = _epsf_table(Path(calib_path))
        ok = np.isfinite(t["sums"]) & (t["sums"] > 0)
        if not ok.any():
            return None
        dx = (x_det - t["xc"]) / np.where(t["xw"] > 0, t["xw"], 1.0)
        dy = (y_det - t["yc"]) / np.where(t["yw"] > 0, t["yw"], 1.0)
        d2 = np.where(ok, dx * dx + dy * dy, np.inf)
        i = int(np.argmin(d2))
        arr = np.nan_to_num(t["epsf"][i], nan=0.0)
        s = arr.sum()
        return (arr / s) if s > 0 else None
    except Exception as e:
        log.warning("ePSF load failed: %s", type(e).__name__)
        return None
