import numpy as np
import pytest

from app.core_types import Stack
from app.science import difference
from app.science import epochs

SHAPE = (41, 41)


def _star(x0, y0, sigma, flux, shape=SHAPE):
    yy, xx = np.mgrid[0:shape[0], 0:shape[1]]
    return flux / (2 * np.pi * sigma ** 2) * np.exp(-0.5 * ((xx - x0) ** 2 + (yy - y0) ** 2) / sigma ** 2)


def _stack(S, V):
    S = np.asarray(S, dtype=np.float32)
    V = np.broadcast_to(np.asarray(V, dtype=np.float32), S.shape).copy()
    return Stack(S=S, V=V, n=np.ones(S.shape, np.int32), mask=~np.isfinite(S))


def test_stack_of_n_frames_reduces_variance_then_zmap_is_unit_normal():
    rng = np.random.default_rng(42)
    sigma, N, shape = 2.0, 4, (100, 100)
    sky = _star(50, 50, 2.0, 500.0, shape)  # identical sky in both epochs

    def make():
        frames = [sky + rng.normal(0, sigma, shape) for _ in range(N)]
        return epochs.stack(frames, [np.full(shape, sigma ** 2)] * N, [np.zeros(shape, bool)] * N)

    a, b = make(), make()
    assert np.allclose(a.V, sigma ** 2 / N, rtol=1e-5)
    res = difference.zmap(a, b, "simple")
    z = res.Z[np.isfinite(res.Z)]
    assert z.size == shape[0] * shape[1]
    assert abs(np.mean(z)) < 0.05
    assert np.std(z) == pytest.approx(1.0, abs=0.05)
    assert res.method == "simple"
    assert "ZOGY" in res.note


def test_identical_stacks_give_zero():
    S = _star(20, 20, 1.5, 300.0)
    res = difference.zmap(_stack(S, 0.01), _stack(S, 0.01))
    assert np.allclose(res.D, 0.0) and np.allclose(res.Z, 0.0)
    assert res.flux_scale == 1.0
    assert res.flux_scale_measured == pytest.approx(1.0, abs=1e-3)


def test_masks_or_combined_and_nan():
    S = np.ones(SHAPE, np.float32)
    a, b = _stack(S, 1.0), _stack(S + 1, 1.0)
    a.S[3, 4] = np.nan
    a.mask[3, 4] = True
    b.S[10, 10] = np.nan
    b.mask[10, 10] = True
    res = difference.zmap(a, b)
    assert np.isnan(res.Z[3, 4]) and np.isnan(res.Z[10, 10])
    assert np.isnan(res.D[3, 4]) and np.isnan(res.D[10, 10])
    assert np.isfinite(res.Z[0, 0])
    assert np.nanmean(res.Z) == pytest.approx(1.0 / np.sqrt(2.0), rel=1e-3)


def test_moving_star_makes_dipole():
    a = _stack(_star(15, 20, 1.5, 1000.0), 0.0025)
    b = _stack(_star(24, 20, 1.5, 1000.0), 0.0025)
    res = difference.zmap(a, b, "simple")
    z = res.Z
    assert z[20, 24] > 20 and z[20, 15] < -20           # + where it went, - where it was
    iy, ix = np.unravel_index(np.nanargmax(z), z.shape)
    ny, nx = np.unravel_index(np.nanargmin(z), z.shape)
    assert (abs(ix - 24) <= 1 and abs(iy - 20) <= 1)
    assert (abs(nx - 15) <= 1 and abs(ny - 20) <= 1)
    # negative -> positive offset points along +x
    assert ix - nx > 5


def test_psf_matched_reduces_residuals_for_unequal_fwhm():
    s_a, s_b = 1.5, 2.2            # sigma in px; a is the sharper one
    rng = np.random.default_rng(3)
    noise = 0.05
    Sa = _star(20, 20, s_a, 1000.0) + rng.normal(0, noise, SHAPE)
    Sb = _star(20, 20, s_b, 1000.0) + rng.normal(0, noise, SHAPE)
    a, b = _stack(Sa, noise ** 2), _stack(Sb, noise ** 2)
    fa, fb = s_a * 2.3548, s_b * 2.3548

    simple = difference.zmap(a, b, "simple")
    matched = difference.zmap(a, b, "psf_matched", fwhm_a_px=fa, fwhm_b_px=fb)
    assert matched.method == "psf_matched"
    assert matched.kernel_sigma_px == pytest.approx(np.sqrt(s_b ** 2 - s_a ** 2), rel=1e-3)
    assert "not ZOGY" in matched.note
    rms_simple = np.sqrt(np.nanmean(simple.D.astype(float) ** 2))
    rms_matched = np.sqrt(np.nanmean(matched.D.astype(float) ** 2))
    assert rms_matched < 0.3 * rms_simple
    # residual is down at the noise level (difference of two noisy frames, plus the smoothed noise of a)
    assert rms_matched < 0.2
    # sharper stack can be b as well
    swapped = difference.zmap(b, a, "psf_matched", fwhm_a_px=fb, fwhm_b_px=fa)
    assert swapped.kernel_sigma_px == pytest.approx(matched.kernel_sigma_px)
    assert np.sqrt(np.nanmean(swapped.D.astype(float) ** 2)) < 0.3 * rms_simple


def test_psf_matched_variance_uses_kernel_squared():
    V = np.full(SHAPE, 4.0, np.float32)
    S = np.zeros(SHAPE, np.float32)
    a, b = _stack(S, V), _stack(S, V)
    res = difference.zmap(a, b, "psf_matched", fwhm_a_px=2.0, fwhm_b_px=6.0)
    # for a uniform variance field, V (*) k^2 (k unit-sum) = V * sum(k^2) away from the edges
    k = difference._gaussian_kernel(res.kernel_sigma_px)
    _, V2 = difference._convolve_stack(S.astype(float), V.astype(float), res.kernel_sigma_px)
    assert V2[20, 20] == pytest.approx(4.0 * float((k ** 2).sum()), rel=1e-6)


def test_psf_matched_skips_tiny_kernel_and_missing_fwhm():
    S = _star(20, 20, 1.5, 300.0)
    a, b = _stack(S, 0.01), _stack(S, 0.01)
    r1 = difference.zmap(a, b, "psf_matched", fwhm_a_px=3.5, fwhm_b_px=3.5)
    assert r1.method == "psf_matched" and "no convolution" in r1.note
    r2 = difference.zmap(a, b, "psf_matched")
    assert r2.method == "simple" and "FWHM missing" in r2.note
    with pytest.raises(ValueError):
        difference.zmap(a, b, "zogy")


def test_flux_scale_measured_and_applied():
    rng = np.random.default_rng(7)
    sig = 0.5
    clean = _star(20, 20, 1.5, 1000.0)
    a = _stack(clean + rng.normal(0, sig, SHAPE), sig ** 2)
    b = _stack(1.2 * clean + rng.normal(0, 1.2 * sig, SHAPE), (1.2 * sig) ** 2)
    res = difference.zmap(a, b, "simple")
    assert res.flux_scale_measured == pytest.approx(1.2, abs=0.03)
    assert res.flux_scale == pytest.approx(res.flux_scale_measured)
    assert np.nanstd(res.Z) < 1.5
    assert "applied" in res.note


def test_flux_scale_not_applied_within_tolerance():
    clean = _star(20, 20, 1.5, 1000.0)
    a = _stack(clean, 0.01)
    b = _stack(1.03 * clean, 0.01)
    res = difference.zmap(a, b, "simple")
    assert res.flux_scale_measured == pytest.approx(1.03, abs=0.005)
    assert res.flux_scale == 1.0
