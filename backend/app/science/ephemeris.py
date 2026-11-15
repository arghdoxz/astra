"""Predicted sky track of a target: proper motion plus annual parallax (SCIENCE_REFERENCE §2.6).

Method (differential GCRS):
  1. Propagate the catalog position with its proper motion (``SkyCoord.apply_space_motion``; the
     distance comes from the parallax so perspective effects are handled).
  2. Parallax-only offset = GCRS(target with distance) - GCRS(same direction, infinite distance) at the
     same obstime.  Aberration and light deflection are common to both and cancel, which leaves only the
     annual parallax displacement for a geocentric observer.
  3. Add that offset to the PM-propagated ICRS position.

Everything is vectorised over the MJD array.
"""
from __future__ import annotations

import warnings
from typing import Optional, Sequence

import numpy as np
import astropy.units as u
from astropy.coordinates import GCRS, Distance, SkyCoord
from astropy.time import Time

from .. import models

_DEFAULT_REF_EPOCH = 2000.0
_MIN_PLX_MAS = 1e-3


def _times(mjds: Sequence[float]) -> Time:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # "dubious year" for future leap-second tables
        return Time(np.atleast_1d(np.asarray(mjds, dtype=float)), format="mjd", scale="utc")


def _wrap_deg(d: np.ndarray) -> np.ndarray:
    return (d + 180.0) % 360.0 - 180.0


def _gcrs_offset_mas(coords: SkyCoord, t: Time) -> tuple[np.ndarray, np.ndarray]:
    """GCRS(coords with distance) - GCRS(same direction at infinity), as (dRA*cosδ, dDec) in mas."""
    frame = GCRS(obstime=t)
    near = coords.transform_to(frame)
    far = SkyCoord(ra=coords.ra, dec=coords.dec, frame="icrs").transform_to(frame)
    dra = _wrap_deg((near.ra - far.ra).to_value(u.deg))
    ddec = (near.dec - far.dec).to_value(u.deg)
    cosd = np.cos(near.dec.to_value(u.rad))
    return dra * cosd * 3.6e6, ddec * 3.6e6


def _track(ra: float, dec: float, pm_ra: Optional[float], pm_dec: Optional[float],
           parallax: Optional[float], ref_epoch: Optional[float], mjds: Sequence[float]
           ) -> tuple[np.ndarray, np.ndarray]:
    mjd_arr = np.atleast_1d(np.asarray(mjds, dtype=float))
    n = mjd_arr.size
    if n == 0:
        return np.empty(0), np.empty(0)
    if not pm_ra and not pm_dec and not parallax:
        return np.full(n, float(ra)), np.full(n, float(dec))

    plx = max(float(parallax), _MIN_PLX_MAS) if parallax else _MIN_PLX_MAS
    epoch = float(ref_epoch) if ref_epoch else _DEFAULT_REF_EPOCH
    t = _times(mjd_arr)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        c = SkyCoord(ra=ra * u.deg, dec=dec * u.deg,
                     pm_ra_cosdec=float(pm_ra or 0.0) * u.mas / u.yr,
                     pm_dec=float(pm_dec or 0.0) * u.mas / u.yr,
                     distance=Distance(parallax=plx * u.mas),
                     obstime=Time(epoch, format="jyear"))
        p = c.apply_space_motion(new_obstime=t)
        # Parallax offset only matters when a real parallax is known; with the 1e-3 mas placeholder it is
        # < 1e-9 arcsec, so computing it is harmless but skip the cost.
        if parallax and parallax > 0:
            dx, dy = _gcrs_offset_mas(p, t)
        else:
            dx = dy = np.zeros(n)
    ra_out = p.ra.to_value(u.deg) + dx / 3.6e6 / np.cos(p.dec.to_value(u.rad))
    dec_out = p.dec.to_value(u.deg) + dy / 3.6e6
    return np.mod(ra_out, 360.0), dec_out


def predict_track(target: models.Target, mjds: list[float]) -> list[tuple[float, float]]:
    """Predicted (ra, dec) in degrees at each MJD (PM + annual parallax; no aberration)."""
    ra, dec = _track(target.ra, target.dec, target.pm_ra, target.pm_dec, target.parallax,
                     target.ref_epoch, mjds)
    return [(float(a), float(b)) for a, b in zip(ra, dec)]


def propagate(ra: float, dec: float, pm_ra: Optional[float], pm_dec: Optional[float],
              parallax: Optional[float], ref_epoch: Optional[float], mjd: float) -> tuple[float, float]:
    """Single-point version of predict_track for raw numbers."""
    r, d = _track(ra, dec, pm_ra, pm_dec, parallax, ref_epoch, [mjd])
    return float(r[0]), float(d[0])


def parallax_factors(ra: float, dec: float, mjds) -> np.ndarray:
    """Parallax factors, shape (n, 2): offset (dRA*cosδ, dDec) per unit parallax (dimensionless).

    Computed as the differential GCRS offset for a 1000 mas parallax divided by 1000, so multiplying by a
    parallax in mas gives an offset in mas.
    """
    mjd_arr = np.atleast_1d(np.asarray(mjds, dtype=float))
    if mjd_arr.size == 0:
        return np.zeros((0, 2))
    t = _times(mjd_arr)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        c = SkyCoord(ra=np.full(mjd_arr.size, float(ra)) * u.deg, dec=np.full(mjd_arr.size, float(dec)) * u.deg,
                     distance=Distance(parallax=1000.0 * u.mas))
        dx, dy = _gcrs_offset_mas(c, t)
    return np.column_stack([dx, dy]) / 1000.0
