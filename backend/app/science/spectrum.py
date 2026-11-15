"""On-the-fly spectrum: bin per-exposure photometry onto the 102-channel SPHEREx grid (SCIENCE_REFERENCE §2.4)."""
from __future__ import annotations

import math
from functools import lru_cache
from typing import Optional

import numpy as np

from .. import models

# Detector wavelength ranges (µm), SCIENCE_REFERENCE §1.
DETECTOR_RANGES: dict[int, tuple[float, float]] = {
    1: (0.75, 1.09), 2: (1.10, 1.62), 3: (1.63, 2.41),
    4: (2.42, 3.82), 5: (3.83, 4.41), 6: (4.42, 5.00),
}
BINS_PER_DETECTOR = 17
FEATURE_NOTE = "reference band — not a detection claim"

# (species, wavelengths µm) from SCIENCE_REFERENCE §2.4.
_FEATURES: list[tuple[str, list[float]]] = [
    ("H2O", [1.4, 1.9, 2.7]),
    ("CH4", [1.65, 2.2, 3.3]),
    ("CO", [2.3, 4.6]),
    ("CO2", [4.3]),
    ("NH3", [3.0]),
    ("H2O ice", [3.0]),
    ("Br-alpha", [4.05]),
    ("Pa-alpha", [1.87]),
    ("Pa-beta", [1.28]),
]


@lru_cache(maxsize=1)
def _grid() -> tuple[tuple[float, ...], tuple[int, ...], dict[int, np.ndarray], dict[int, int]]:
    centres: list[float] = []
    dets: list[int] = []
    edges: dict[int, np.ndarray] = {}
    first: dict[int, int] = {}
    for d, (lo, hi) in DETECTOR_RANGES.items():
        e = np.geomspace(lo, hi, BINS_PER_DETECTOR + 1)
        edges[d] = e
        first[d] = len(centres)
        centres.extend(float(c) for c in np.sqrt(e[:-1] * e[1:]))
        dets.extend([d] * BINS_PER_DETECTOR)
    return tuple(centres), tuple(dets), edges, first


def channel_grid() -> tuple[list[float], list[int]]:
    """102 channel centres (17 per detector, equal log-λ steps) and the detector of each channel."""
    c, d, _, _ = _grid()
    return list(c), list(d)


def bin_index(detector: int, wavelength_um: float) -> Optional[int]:
    """Index (0..101) of the channel holding ``wavelength_um`` within ``detector``'s range, else None."""
    _, _, edges, first = _grid()
    if detector not in edges or wavelength_um is None or not math.isfinite(wavelength_um):
        return None
    e = edges[detector]
    if wavelength_um < e[0] or wavelength_um > e[-1]:
        return None
    k = int(np.searchsorted(e, wavelength_um, side="right")) - 1
    k = min(max(k, 0), BINS_PER_DETECTOR - 1)
    return first[detector] + k


def spectral_features() -> list[models.SpectralFeature]:
    return [models.SpectralFeature(species=s, wavelength_um=w, note=FEATURE_NOTE)
            for s, ws in _FEATURES for w in ws]


def _visit_order(phot: list[models.PhotPoint]) -> list[str]:
    mjds: dict[str, list[float]] = {}
    for p in phot:
        mjds.setdefault(p.visit_id, []).append(p.mjd)
    return sorted(mjds, key=lambda v: (float(np.mean(mjds[v])), v))


def build_spectrum(phot: list[models.PhotPoint], wavelength_source: str = "wcs_wave") -> models.Spectrum:
    """One series per visit on the 102-channel grid.

    Per channel: inverse-variance weighted mean of unsaturated, non-outlier points with a flux and error.
    If the channel only has saturated points, ``saturated=True`` and flux is the largest lower limit
    (error None).  Channels with nothing stay ``flux_ujy=None`` (a gap, never interpolated).
    """
    centres, dets = channel_grid()
    nb = len(centres)
    visits_out: list[models.SpectrumVisit] = []
    for vid in _visit_order(phot):
        good: list[list[models.PhotPoint]] = [[] for _ in range(nb)]
        sat: list[list[models.PhotPoint]] = [[] for _ in range(nb)]
        for p in phot:
            if p.visit_id != vid or p.flux_ujy is None or not math.isfinite(p.flux_ujy):
                continue
            k = bin_index(p.detector, p.wavelength_um)
            if k is None:
                continue
            if p.saturated:
                sat[k].append(p)
            elif not p.outlier and p.flux_err_ujy is not None and p.flux_err_ujy > 0:
                good[k].append(p)
        pts: list[models.SpectrumPointOut] = []
        for k in range(nb):
            if good[k]:
                f = np.array([q.flux_ujy for q in good[k]], dtype=float)
                w = 1.0 / np.array([q.flux_err_ujy for q in good[k]], dtype=float) ** 2
                pts.append(models.SpectrumPointOut(
                    wavelength_um=centres[k], flux_ujy=float((w * f).sum() / w.sum()),
                    flux_err_ujy=float(1.0 / math.sqrt(w.sum())), n=len(good[k]), saturated=False,
                    obs_ids=[q.obs_id for q in good[k]]))
            elif sat[k]:
                pts.append(models.SpectrumPointOut(
                    wavelength_um=centres[k], flux_ujy=float(max(q.flux_ujy for q in sat[k])),
                    flux_err_ujy=None, n=len(sat[k]), saturated=True, obs_ids=[q.obs_id for q in sat[k]]))
            else:
                pts.append(models.SpectrumPointOut(wavelength_um=centres[k], flux_ujy=None, n=0))
        visits_out.append(models.SpectrumVisit(visit_id=vid, points=pts))
    src = "sia_band_center" if wavelength_source == "sia_band_center" else "wcs_wave"
    return models.Spectrum(channels_um=centres, channel_detector=dets, visits=visits_out,
                           features=spectral_features(), wavelength_source=src)
