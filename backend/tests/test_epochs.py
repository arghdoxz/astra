from pathlib import Path

import numpy as np
import pytest
from astropy.io import fits
from astropy.wcs import WCS

from app.core_types import CutoutData
from app.science import epochs
from app.science import flags as F

FIXTURE = Path(__file__).parent / "fixtures" / "dr1_D6_barnard_0p02deg.fits"
RA, DEC = 269.452, 4.6934


def _gauss(shape, x0, y0, sigma, amp):
    yy, xx = np.mgrid[0:shape[0], 0:shape[1]]
    return amp * np.exp(-0.5 * ((xx - x0) ** 2 + (yy - y0) ** 2) / sigma ** 2)


def _cutout(grid_like, image, variance, raw_flags=None, obs_id="o1", fwhm=6.5):
    if raw_flags is None:
        raw_flags = np.zeros(image.shape, dtype=np.int32)
    hard = F.hard_mask(raw_flags)
    image = image.astype(np.float32).copy()
    variance = variance.astype(np.float32).copy()
    image[hard] = np.nan
    variance[hard] = np.nan
    return CutoutData(
        obs_id=obs_id, path=Path("synthetic.fits"), image=image, variance=variance, raw_flags=raw_flags,
        hard=hard, header=fits.Header(), wcs=grid_like.wcs, mjd=60000.0, detector=1, version="test",
        psf_fwhm_arcsec=fwhm, flag_names=dict(F.DEFAULT_BIT_NAMES), background_method="median",
    )


def test_make_grid_centre_and_orientation():
    g = epochs.make_grid(RA, DEC, 3.0)
    ny, nx = g.shape
    assert ny == nx and ny % 2 == 1
    assert ny >= int(np.ceil(3.0 * 60 / 6.15))
    c = (nx - 1) / 2.0  # 0-based centre pixel
    ra, dec = g.wcs.all_pix2world(c, c, 0)
    assert ra == pytest.approx(RA, abs=1e-9)
    assert dec == pytest.approx(DEC, abs=1e-9)
    assert g.wcs.wcs.crpix[0] == pytest.approx((nx + 1) / 2.0)
    # east is left: RA decreases with x; north is up: Dec increases with y
    ra1, _ = g.wcs.all_pix2world(c + 5, c, 0)
    _, dec1 = g.wcs.all_pix2world(c, c + 5, 0)
    assert ra1 < RA and dec1 > DEC
    assert abs(g.wcs.wcs.cdelt[0]) * 3600 == pytest.approx(6.15)
    assert g.wcs.wcs.cdelt[0] < 0 < g.wcs.wcs.cdelt[1]
    assert g.to_model().width == nx


def test_make_grid_exact_and_even_sizes():
    g = epochs.make_grid(RA, DEC, 41 * 6.15 / 60.0)
    assert g.shape == (41, 41)
    g2 = epochs.make_grid(RA, DEC, 40 * 6.15 / 60.0)  # exactly 40 -> rounded up to odd 41
    assert g2.shape == (41, 41)


def test_stack_variance_reduces_by_n():
    rng = np.random.default_rng(1)
    sigma, N, shape = 3.0, 5, (120, 120)
    imgs = [rng.normal(10.0, sigma, shape) for _ in range(N)]
    vs = [np.full(shape, sigma ** 2) for _ in range(N)]
    ms = [np.zeros(shape, bool) for _ in range(N)]
    st = epochs.stack(imgs, vs, ms)
    assert st.S.dtype == np.float32 and st.V.dtype == np.float32
    assert np.allclose(st.V, sigma ** 2 / N, rtol=1e-5)
    assert np.all(st.n == N) and not st.mask.any()
    # empirical scatter of the stack matches V_S
    assert np.var(st.S) == pytest.approx(sigma ** 2 / N, rel=0.1)


def test_stack_weighting_and_masking():
    shape = (2, 2)
    a = np.array([[1.0, 2.0], [3.0, np.nan]])
    b = np.array([[3.0, 2.0], [5.0, np.nan]])
    va = np.array([[1.0, 1.0], [1.0, 1.0]])
    vb = np.array([[3.0, 1.0], [0.0, 1.0]])      # V<=0 ignored at [1,0]
    ma = np.zeros(shape, bool)
    mb = np.zeros(shape, bool)
    mb[0, 1] = True                                # masked at [0,1]
    st = epochs.stack([a, b], [va, vb], [ma, mb])
    # [0,0]: weights 1 and 1/3 -> (1 + 3/3)/(1+1/3) = 1.5 ; V = 1/(4/3) = 0.75
    assert st.S[0, 0] == pytest.approx(1.5) and st.V[0, 0] == pytest.approx(0.75)
    assert st.n[0, 1] == 1 and st.S[0, 1] == pytest.approx(2.0)
    assert st.n[1, 0] == 1 and st.S[1, 0] == pytest.approx(3.0)
    assert st.n[1, 1] == 0 and st.mask[1, 1] and np.isnan(st.S[1, 1]) and np.isnan(st.V[1, 1])
    assert st.mask.sum() == 1


def test_reproject_cutout_keeps_star_position_and_masks():
    grid = epochs.make_grid(RA, DEC, 3.0)  # 31 x 31
    big = epochs.make_grid(RA, DEC, 41 * 6.15 / 60.0)  # same orientation/scale, 41 x 41, centre pixel 20
    assert big.shape == (41, 41) and grid.shape == (31, 31)
    img = _gauss(big.shape, 23, 18, 1.5, 100.0)
    var = np.full(big.shape, 0.25)
    flags = np.zeros(big.shape, np.int32)
    flags[18, 25] = 1 << 10       # HOT (hard) at cutout (x=25, y=18) -> grid (20, 13)
    flags[10, 12] = 1 << 17       # PERSIST (contamination) at cutout (12, 10) -> grid (7, 5)
    flags[20, 20] = 1 << 1        # OVERFLOW (hard + saturation) at the centre
    cut = _cutout(big, img, var, flags)

    I, V, m = epochs.reproject_cutout(cut, grid)
    assert I.shape == V.shape == m.shape == grid.shape
    assert I.dtype == np.float32 and V.dtype == np.float32 and m.dtype == bool
    iy, ix = np.unravel_index(np.nanargmax(I), I.shape)
    assert (ix, iy) == (18, 13)                       # 23-5, 18-5
    assert m[13, 20]                                  # hard-masked pixel -> NaN -> masked
    assert np.isnan(I[13, 20])

    hard, contam, sat = epochs.reproject_flags(cut, grid)
    assert hard[13, 20] and hard[15, 15] and not hard[13, 18]
    assert contam[5, 7] and contam.sum() == 1
    assert sat[15, 15] and sat.sum() == 1

    st = epochs.stack_cutouts([cut, _cutout(big, img, var, None, obs_id="o2", fwhm=7.5)], grid)
    assert st.obs_ids == ["o1", "o2"]
    assert st.fwhm_arcsec == pytest.approx(7.0)
    assert st.contam is not None and st.contam[5, 7]
    assert st.n[13, 20] == 1 and st.n[13, 18] == 2


def test_reproject_fixture_cutout():
    with fits.open(FIXTURE) as h:
        hdr = h["IMAGE"].header.copy()
        img = h["IMAGE"].data.astype(np.float32)
        var = h["VARIANCE"].data.astype(np.float32)
        raw = h["FLAGS"].data.astype(np.int32)
    w = WCS(hdr, naxis=2)
    ny, nx = img.shape
    ra, dec = w.all_pix2world((nx - 1) / 2.0, (ny - 1) / 2.0, 0)
    hard = F.hard_mask(raw)
    img = np.where(hard, np.nan, img - np.nanmedian(img))
    var = np.where(hard, np.nan, var)
    cut = CutoutData(obs_id="fx", path=FIXTURE, image=img, variance=var, raw_flags=raw, hard=hard, header=hdr,
                     wcs=w, mjd=60000.0, detector=6, version="test", psf_fwhm_arcsec=6.0,
                     flag_names=F.parse_mask_names(None), background_method="median")
    grid = epochs.make_grid(float(ra), float(dec), 0.8)
    I, V, m = epochs.reproject_cutout(cut, grid)
    assert I.shape == grid.shape
    assert (~m).any() and np.isfinite(I[~m]).all()
    hmask, cmask, smask = epochs.reproject_flags(cut, grid)
    assert hmask.shape == cmask.shape == smask.shape == grid.shape
