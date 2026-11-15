"""PNG rendering with numpy + Pillow (no matplotlib).

Orientation: arrays are ``[y, x]`` with y increasing north. PNGs are written top row first, so every writer
flips vertically (PNG row r <-> y = height-1-r; API_CONTRACT "Pixel convention"). Images are written at native
grid resolution; upsampling is done client-side (pixelated).
"""
from __future__ import annotations

import warnings
from pathlib import Path

import numpy as np
from PIL import Image

NAN_RGB = (14, 18, 32)  # slightly blue-tinted dark, used for NaN / no-data pixels


def shared_stretch(arrays: list[np.ndarray]) -> tuple[float, float]:
    """(vmin, vmax) = 1st and 99.5th nan-percentiles of the pixelwise median of ``arrays``.

    Use one result for all visits of a detector so blinking does not fake variability.
    All-NaN / empty input returns (0.0, 1.0); a degenerate range is widened to vmax = vmin + 1.
    """
    if not arrays:
        return 0.0, 1.0
    cube = np.stack([np.asarray(a, dtype=np.float64) for a in arrays], axis=0)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        med = np.nanmedian(cube, axis=0)
    fin = med[np.isfinite(med)]
    if fin.size == 0:
        return 0.0, 1.0
    vmin, vmax = np.percentile(fin, [1.0, 99.5])
    vmin, vmax = float(vmin), float(vmax)
    if not vmax > vmin:
        vmax = vmin + 1.0
    return vmin, vmax


def _save(rgb: np.ndarray, path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # mode is inferred from the shape: (h, w, 3) -> RGB, (h, w, 4) -> RGBA (the `mode=` argument is deprecated)
    Image.fromarray(np.ascontiguousarray(np.flipud(rgb))).save(path, format="PNG", optimize=True)


def asinh_stretch(img: np.ndarray, vmin: float, vmax: float) -> np.ndarray:
    """asinh stretch to [0, 1]: y = asinh((x - vmin)/s) / asinh((vmax - vmin)/s), s = 0.1*(vmax - vmin), clipped.

    s sets the transition from linear to logarithmic response (10% of the display range). NaN stays NaN.
    """
    x = np.asarray(img, dtype=np.float64)
    rng = float(vmax) - float(vmin)
    if not rng > 0:
        rng = 1.0
    s = 0.1 * rng
    with np.errstate(invalid="ignore"):
        y = np.arcsinh((x - vmin) / s) / np.arcsinh(rng / s)
    return np.clip(y, 0.0, 1.0)  # clip keeps NaN as NaN


def to_png(img: np.ndarray, vmin: float, vmax: float, path: Path) -> None:
    """8-bit grayscale (stored as RGB) asinh image; NaN -> RGB(14,18,32); flipped so row 0 is north."""
    y = asinh_stretch(img, vmin, vmax)
    bad = ~np.isfinite(y)
    g = np.rint(np.nan_to_num(y, nan=0.0) * 255.0).astype(np.uint8)
    rgb = np.repeat(g[..., None], 3, axis=2)
    rgb[bad] = NAN_RGB
    _save(rgb, path)


# Diverging colormap anchors at t in [-1, 1]: blue (negative) -> near-black (zero) -> orange/red (positive).
_CM_T = np.array([-1.0, -0.5, 0.0, 0.5, 1.0])
_CM_RGB = np.array([
    [90, 160, 255],
    [30, 80, 190],
    [8, 8, 12],
    [200, 70, 25],
    [255, 170, 60],
], dtype=np.float64)


def zmap_png(z: np.ndarray, path: Path, clip: float = 8.0) -> None:
    """Diverging Z-map PNG clipped at +/- ``clip`` sigma; NaN -> RGB(14,18,32); flipped north-up."""
    z = np.asarray(z, dtype=np.float64)
    t = np.clip(z / float(clip), -1.0, 1.0)
    bad = ~np.isfinite(t)
    t0 = np.nan_to_num(t, nan=0.0)
    rgb = np.stack([np.interp(t0, _CM_T, _CM_RGB[:, k]) for k in range(3)], axis=-1)
    rgb = np.rint(rgb).astype(np.uint8)
    rgb[bad] = NAN_RGB
    _save(rgb, path)


def flags_png(hard: np.ndarray, contam: np.ndarray, path: Path) -> None:
    """RGBA overlay: red (230,60,60,170) hard-masked, yellow (240,200,40,150) contamination, else transparent.

    Hard-masked wins where both are set. Flipped north-up.
    """
    hard = np.asarray(hard, dtype=bool)
    contam = np.asarray(contam, dtype=bool)
    if hard.shape != contam.shape:
        raise ValueError("hard and contam must have the same shape")
    rgba = np.zeros(hard.shape + (4,), dtype=np.uint8)
    rgba[contam] = (240, 200, 40, 150)
    rgba[hard] = (230, 60, 60, 170)
    _save(rgba, path)
