"""SPHEREx cutout download (ePSF-skip streaming) and loading (ARCHITECTURE section 3).

Observed on the live service (2026-11-15): the HDU order of a cutout response is
``PRIMARY, IMAGE, FLAGS, VARIANCE, ZODI, EPSF, WCS-WAVE``. The EPSF table (~3.9 MB) is what makes cutouts heavy,
so the streaming reader keeps every HDU *before* EPSF (including ZODI) and closes the connection as soon as the
EPSF header arrives. The per-detector EPSF / WCS-WAVE tables are fetched once by ``calib_cache``.
"""
from __future__ import annotations

import asyncio
import logging
import math
import re
import warnings
from pathlib import Path
from typing import AsyncIterable, Iterable, Optional

import httpx
import numpy as np
from astropy.io import fits
from astropy.stats import sigma_clipped_stats
from astropy.wcs import WCS

from .. import models
from ..config import get_settings
from ..core_types import CutoutData
from . import cache
from .http import check_allowed, fetch, stream

log = logging.getLogger("astra.cutouts")

BLOCK = 2880
KEEP_HDUS = frozenset({"PRIMARY", "IMAGE", "FLAGS", "VARIANCE", "ZODI"})
STOP_HDU = "EPSF"

# Private copy of the flag tables (DATA_SOURCES section 1.4) so this module has no dependency on science/flags.py.
_HARD_BITS = (0, 1, 2, 6, 9, 10, 11, 15, 19)  # SOURCE (21) is informational and never masked
_HARD_MASK_INT = sum(1 << b for b in _HARD_BITS)
_DEFAULT_FLAG_NAMES = {
    0: "TRANSIENT", 1: "OVERFLOW", 2: "SUR_ERROR", 6: "NONFUNC", 7: "DICHROIC", 9: "MISSING_DATA", 10: "HOT",
    11: "COLD", 12: "FULLSAMPLE", 14: "PHANMISS", 15: "NONLINEAR", 17: "PERSIST", 19: "OUTLIER",
    20: "CROSSTALK", 21: "SOURCE", 22: "GHOST", 23: "GHOST_FPA", 24: "GHOST_EXT", 25: "STREAK", 26: "BLOOM",
    27: "SNOWBALL", 28: "HALO",
}
# Rough PSF FWHM (arcsec) used only when the PSF_FWHM header card is missing; measured D6 = 9.04" (fixture),
# short-wavelength detectors are ~6-7" (SCIENCE_REFERENCE section 1).
_DEFAULT_PSF_FWHM = {1: 6.4, 2: 6.4, 3: 6.5, 4: 7.0, 5: 8.5, 6: 9.0}


# ------------------------------------------------------------------------------------------ streaming FITS reader
class FitsTruncator:
    """Incremental FITS reader: keeps the bytes of ``keep`` HDUs, stops at the ``stop_at`` extension.

    Feed arbitrary chunks with ``feed()``; once ``done`` is True (stop HDU header seen) no more input is needed.
    ``result()`` returns a valid FITS byte string made of the kept HDUs.
    """

    def __init__(self, keep: Iterable[str] = KEEP_HDUS, stop_at: str = STOP_HDU) -> None:
        self.keep = frozenset(keep)
        self.stop_at = stop_at
        self.done = False
        self.kept: list[str] = []
        self._buf = bytearray()
        self._out = bytearray()
        self._hdr = bytearray()
        self._state = "header"  # header | data
        self._skip = 0  # bytes of data still to consume
        self._keep_data = False
        self._n_hdu = 0

    @staticmethod
    def _is_end_block(block: bytes) -> bool:
        for i in range(0, BLOCK, 80):
            card = block[i:i + 80]
            if card[:3] == b"END" and not card[3:].strip():
                return True
        return False

    def feed(self, chunk: bytes) -> None:
        if self.done:
            return
        self._buf += chunk
        while not self.done:
            if self._state == "header":
                if len(self._buf) < BLOCK:
                    return
                block = bytes(self._buf[:BLOCK])
                del self._buf[:BLOCK]
                if self._n_hdu == 0 and not self._hdr and not block.startswith(b"SIMPLE"):
                    raise ValueError("not a FITS stream")
                self._hdr += block
                if self._is_end_block(block):
                    self._finish_header()
            else:
                if self._skip == 0:
                    self._state = "header"
                    continue
                take = min(self._skip, len(self._buf))
                if take == 0:
                    return
                if self._keep_data:
                    self._out += self._buf[:take]
                del self._buf[:take]
                self._skip -= take
                if self._skip == 0:
                    self._state = "header"

    def _finish_header(self) -> None:
        hdr = fits.Header.fromstring(self._hdr.decode("ascii", "replace"))
        raw = bytes(self._hdr)
        self._hdr = bytearray()
        name = "PRIMARY" if self._n_hdu == 0 else str(hdr.get("EXTNAME", f"HDU{self._n_hdu}")).strip().upper()
        self._n_hdu += 1
        if name == self.stop_at:
            self.done = True
            return
        naxis = int(hdr.get("NAXIS", 0))
        nbytes = 0
        if naxis > 0:
            npix = 1
            for i in range(1, naxis + 1):
                npix *= int(hdr[f"NAXIS{i}"])
            nbytes = abs(int(hdr["BITPIX"])) // 8 * int(hdr.get("GCOUNT", 1)) * (int(hdr.get("PCOUNT", 0)) + npix)
        padded = int(math.ceil(nbytes / BLOCK)) * BLOCK
        self._keep_data = name in self.keep
        if self._keep_data:
            self._out += raw
            self.kept.append(name)
        self._skip = padded
        self._state = "data"

    def result(self) -> bytes:
        """The kept HDUs as FITS bytes. Raises ValueError if the stream ended in the middle of an HDU."""
        if not self.done and (self._buf or self._hdr or (self._state == "data" and self._skip > 0)):
            raise ValueError("cutout stream ended in the middle of an HDU")
        if not self.kept:
            raise ValueError("no usable HDUs in cutout stream")
        return bytes(self._out)


async def truncate_stream(chunks: AsyncIterable[bytes]) -> tuple[bytes, list[str]]:
    """Run ``FitsTruncator`` over an async chunk iterator; stops consuming once EPSF is reached.

    Returns ``(fits_bytes, kept_hdu_names)``.
    """
    p = FitsTruncator()
    async for chunk in chunks:
        p.feed(chunk)
        if p.done:
            break
    return p.result(), p.kept


# ------------------------------------------------------------------------------------------ downloading
_sems: dict[int, asyncio.Semaphore] = {}


def _semaphore() -> asyncio.Semaphore:
    """Cutout concurrency limiter, created lazily per running event loop."""
    loop_id = id(asyncio.get_running_loop())
    sem = _sems.get(loop_id)
    if sem is None:
        _sems.clear()  # drop semaphores of dead loops
        sem = _sems[loop_id] = asyncio.Semaphore(max(1, get_settings().cutout_concurrency))
    return sem


def _cutout_params(ra: float, dec: float, size_deg: float) -> dict[str, str]:
    return {"center": f"{ra:.6f},{dec:.6f}", "size": f"{size_deg:g}"}


async def _download_stream(url: str, params: dict[str, str]) -> tuple[bytes, list[str]]:
    last: Optional[Exception] = None
    for attempt in range(3):
        try:
            async with stream("GET", url, params=params, timeout=60) as resp:
                return await truncate_stream(resp.aiter_bytes(65536))
        except (httpx.TransportError, ValueError) as e:
            if isinstance(e, ValueError) and "allow-listed" in str(e):
                raise
            last = e
            await asyncio.sleep((1.0, 3.0, 9.0)[attempt])
    assert last is not None
    raise last


async def download_full(exp: models.Exposure, ra: float, dec: float, size_deg: float) -> bytes:
    """Whole cutout response (all HDUs, ~3.9 MB incl. EPSF + WCS-WAVE). Respects the cutout concurrency limit."""
    check_allowed(exp.access_url)
    async with _semaphore():
        resp = await fetch("GET", exp.access_url, params=_cutout_params(ra, dec, size_deg), timeout=120, retries=3)
    return resp.content


async def fetch_cutout(exp: models.Exposure, ra: float, dec: float, size_deg: float) -> Path:
    """Download (or reuse) the cutout of ``exp`` centred on (ra, dec); returns the cached FITS path.

    ``CUTOUT_MODE=stream`` (default): keeps PRIMARY/IMAGE/FLAGS/VARIANCE/ZODI, drops EPSF/WCS-WAVE.
    ``CUTOUT_MODE=full``: stores the whole response. Raises on failure (caller marks the exposure "failed").
    """
    path = cache.cache_path("cutouts", cache.key_of(exp.did, ra, dec, size_deg), "fits")
    try:
        if path.stat().st_size > 0:
            return path
    except OSError:
        pass
    check_allowed(exp.access_url)
    params = _cutout_params(ra, dec, size_deg)
    if get_settings().cutout_mode == "full":
        data = await download_full(exp, ra, dec, size_deg)
    else:
        async with _semaphore():
            data, kept = await _download_stream(exp.access_url, params)
        if "IMAGE" not in kept:
            raise ValueError(f"cutout for {exp.did} has no IMAGE HDU")
    cache.atomic_write_bytes(path, data)
    return path


# ------------------------------------------------------------------------------------------ loading
def _parse_flag_names(header: fits.Header) -> dict[int, str]:
    names: dict[int, str] = {}
    for key in header:
        m = re.fullmatch(r"MSKN(\d{4})", str(key))
        if m:
            names[int(m.group(1))] = str(header[key]).strip()
    return names


def hard_mask_of(flags: np.ndarray) -> np.ndarray:
    """True where any hard-mask bit (0,1,2,6,9,10,11,15,19) is set."""
    return (flags.astype(np.int64) & _HARD_MASK_INT) != 0


def load_cutout(path: Path, exp: models.Exposure) -> CutoutData:
    """Read a cached cutout into ``CutoutData`` (image - zodi - sigma-clipped median, hard-masked -> NaN)."""
    with fits.open(path, memmap=False) as hdul:
        primary = hdul[0].header
        img_hdu = hdul["IMAGE"]
        header = img_hdu.header.copy()
        image = np.array(img_hdu.data, dtype=np.float32)
        raw_flags = np.array(hdul["FLAGS"].data, dtype=np.int32) if "FLAGS" in hdul else np.zeros(image.shape, np.int32)
        variance = (np.array(hdul["VARIANCE"].data, dtype=np.float32)
                    if "VARIANCE" in hdul else np.full(image.shape, np.nan, np.float32))
        zodi = np.array(hdul["ZODI"].data, dtype=np.float32) if "ZODI" in hdul else None
        flag_hdr = hdul["FLAGS"].header if "FLAGS" in hdul else fits.Header()
        flag_names = _parse_flag_names(flag_hdr) or _parse_flag_names(header) or dict(_DEFAULT_FLAG_NAMES)
        version = str(primary.get("VERSION") or header.get("VERSION") or exp.pipeline_version or "unknown").strip()

    # Make the IMAGE header self-describing (VERSION lives in PRIMARY, MSKN cards in FLAGS).
    if "VERSION" not in header:
        header["VERSION"] = version
    for bit, name in flag_names.items():
        card = f"MSKN{bit:04d}"
        if card not in header:
            header[card] = name

    hard = hard_mask_of(raw_flags) | ~np.isfinite(image)
    has_zodi = zodi is not None and zodi.shape == image.shape
    if has_zodi:
        image = image - zodi
    valid = ~hard & np.isfinite(image)
    if valid.sum() >= 3:
        _, med, _ = sigma_clipped_stats(image[valid].astype(np.float64), sigma=3.0, maxiters=5)
        if np.isfinite(med):
            image = (image - np.float32(med)).astype(np.float32)
    image = np.where(hard, np.nan, image).astype(np.float32)
    variance = np.where(hard, np.nan, variance).astype(np.float32)

    detector = int(header.get("DETECTOR", exp.detector))
    psf = header.get("PSF_FWHM")
    psf_fwhm = float(psf) if psf is not None and np.isfinite(float(psf)) else _DEFAULT_PSF_FWHM.get(detector, 8.0)
    mjd = header.get("MJD-AVG")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        wcs = WCS(header, naxis=2)
    return CutoutData(
        obs_id=exp.obs_id, path=Path(path), image=image, variance=variance, raw_flags=raw_flags, hard=hard,
        header=header, wcs=wcs, mjd=float(mjd) if mjd is not None else float(exp.mjd), detector=detector,
        version=version, psf_fwhm_arcsec=psf_fwhm, flag_names=flag_names,
        background_method="zodi+median" if has_zodi else "median", has_zodi=has_zodi,
    )
