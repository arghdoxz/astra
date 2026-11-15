import numpy as np
import pytest
from PIL import Image

from app.science import render


def test_shared_stretch_basic_and_all_nan():
    rng = np.random.default_rng(0)
    a = rng.normal(0, 1, (50, 50))
    b = a + rng.normal(0, 0.01, (50, 50))
    vmin, vmax = render.shared_stretch([a, b])
    assert vmin < vmax
    med = np.nanmedian(np.stack([a, b]), axis=0)
    assert vmin == pytest.approx(np.percentile(med, 1.0))
    assert vmax == pytest.approx(np.percentile(med, 99.5))
    nan = np.full((4, 4), np.nan)
    assert render.shared_stretch([nan, nan]) == (0.0, 1.0)
    assert render.shared_stretch([]) == (0.0, 1.0)
    flat = render.shared_stretch([np.ones((4, 4))])
    assert flat[1] > flat[0]


def test_shared_stretch_ignores_nan_in_one_member():
    a = np.arange(100, dtype=float).reshape(10, 10)
    b = a.copy()
    b[0, 0] = np.nan
    vmin, vmax = render.shared_stretch([a, b])
    assert np.isfinite(vmin) and np.isfinite(vmax)


def test_to_png_size_and_north_up_flip(tmp_path):
    h, w = 5, 7
    img = np.zeros((h, w), dtype=np.float32)
    img[h - 1, 2] = 1.0       # brightest pixel at y = max (north edge)
    img[0, 5] = np.nan        # NaN at y = 0 (south edge)
    out = tmp_path / "sub" / "a.png"
    render.to_png(img, 0.0, 1.0, out)
    im = Image.open(out)
    assert im.size == (w, h)
    arr = np.asarray(im.convert("RGB"))
    assert tuple(arr[0, 2]) == (255, 255, 255)          # y = max -> PNG row 0
    assert tuple(arr[h - 1, 5]) == render.NAN_RGB      # y = 0 -> last PNG row
    assert tuple(arr[3, 0]) == (0, 0, 0)               # zero level -> black


def test_asinh_stretch_properties():
    x = np.array([-1.0, 0.0, 0.5, 1.0, 5.0, np.nan])
    y = render.asinh_stretch(x, 0.0, 1.0)
    assert y[0] == 0.0 and y[1] == 0.0 and y[3] == pytest.approx(1.0) and y[4] == 1.0
    assert 0.5 < y[2] < 1.0           # asinh lifts mid-tones above linear
    assert np.isnan(y[5])


def test_zmap_png_colours(tmp_path):
    z = np.zeros((4, 6))
    z[3, 1] = 20.0     # clipped to +8 sigma
    z[3, 4] = -20.0
    z[0, 0] = np.nan
    out = tmp_path / "z.png"
    render.zmap_png(z, out)
    im = Image.open(out)
    assert im.size == (6, 4)
    arr = np.asarray(im.convert("RGB")).astype(int)
    pos, neg, zero = arr[0, 1], arr[0, 4], arr[2, 2]   # y=3 -> PNG row 0
    assert pos[0] > pos[2]            # orange/red
    assert neg[2] > neg[0]            # blue
    assert zero.max() < 30            # near black
    assert tuple(arr[3, 0]) == render.NAN_RGB


def test_flags_png_overlay(tmp_path):
    hard = np.zeros((3, 4), bool)
    contam = np.zeros((3, 4), bool)
    hard[0, 0] = True
    contam[0, 1] = True
    hard[2, 3] = contam[2, 3] = True
    out = tmp_path / "f.png"
    render.flags_png(hard, contam, out)
    im = Image.open(out)
    assert im.mode == "RGBA" and im.size == (4, 3)
    arr = np.asarray(im)
    assert tuple(arr[2, 0]) == (230, 60, 60, 170)      # y=0 -> bottom row
    assert tuple(arr[2, 1]) == (240, 200, 40, 150)
    assert tuple(arr[0, 3]) == (230, 60, 60, 170)      # hard wins over contam
    assert arr[1, 1, 3] == 0                           # transparent elsewhere
