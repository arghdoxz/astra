"""LIVE verification of the ePSF-skip design (ARCHITECTURE section 3, step 6).

For two exposures of the same detector, at different cutout centres near Eps Ind B, compare lambda(x, y) taken from
the *full* cutout's own WCS-WAVE table with lambda from the *stream-truncated* cutout plus the cached per-detector
calibration table. They must agree within 1 nm. Run with ``uv run pytest -m live tests/test_epsf_skip.py``.
"""
from __future__ import annotations

import io
import math
import warnings

import numpy as np
import pytest
from astropy.io import fits
from astropy.wcs import WCS

from app.config import get_settings
from app.services import calib_cache, cutouts, irsa_sia
from app.services.calib_cache import _strip_sip

pytestmark = pytest.mark.live

EPS_IND_B = (331.04415, -56.78284)
DETECTOR = 6
SIZE_DEG = 0.04
# (dRA*cos(dec), dDec) offsets of the two cutout centres in degrees; the target stays inside both cutouts
OFFSETS = [(0.0, 0.0), (0.008, -0.006)]
TOL_UM = 1e-3  # 1 nm


def _lambda_from_full(hdul: fits.HDUList, ra: float, dec: float) -> tuple[float, float]:
    """lambda, bandwidth (um) from the cutout's own WCS-WAVE (reference computation, IRSA tutorial method)."""
    hdr = hdul["IMAGE"].header
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        cel = WCS(hdr, naxis=2)
        x, y = cel.all_world2pix([[ra, dec]], 0)[0]
        ny, nx = hdul["IMAGE"].data.shape
        x, y = float(np.clip(x, 0, nx - 1)), float(np.clip(y, 0, ny - 1))
        w = WCS(_strip_sip(hdr), fobj=hdul, key="W")
        lam, bw = w.all_pix2world([[x, y]], 0)[0]
    return float(lam), float(bw)


async def _full_and_truncated(exp, ra, dec, tmp_path, tag):
    raw = await cutouts.download_full(exp, ra, dec, SIZE_DEG)
    full = fits.open(io.BytesIO(raw), memmap=False)
    assert {"EPSF", "WCS-WAVE"} <= {h.name for h in full}
    params = cutouts._cutout_params(ra, dec, SIZE_DEG)
    data, kept = await cutouts._download_stream(exp.access_url, params)
    assert "EPSF" not in kept and "WCS-WAVE" not in kept and "IMAGE" in kept
    assert len(data) < len(raw) / 10, "stream mode should skip the multi-MB ePSF table"
    path = tmp_path / f"trunc_{tag}.fits"
    path.write_bytes(data)
    return full, cutouts.load_cutout(path, exp)


async def test_lambda_equivalence_full_vs_truncated_plus_calib(tmp_path):
    exps, status = await irsa_sia.query_exposures(*EPS_IND_B, ["spherex_dr1"])
    assert status["spherex_dr1"] == "ok"
    d6 = [e for e in exps if e.detector == DETECTOR]
    assert len(d6) >= 2, "need two D6 exposures covering Eps Ind B"
    # two exposures far apart in time (different visits / dithers => different detector positions)
    exp_a, exp_b = d6[0], d6[len(d6) // 2]
    assert exp_a.did != exp_b.did

    cuts = []
    for exp, (dx, dy) in zip((exp_a, exp_b), OFFSETS):
        ra = EPS_IND_B[0] + dx / math.cos(math.radians(EPS_IND_B[1]))
        dec = EPS_IND_B[1] + dy
        full, trunc = await _full_and_truncated(exp, ra, dec, tmp_path, exp.obs_id)
        cuts.append((exp, ra, dec, full, trunc))

    # calibration cached from exposure A is re-used for exposure B (same detector and pipeline VERSION)
    versions = {c[4].version for c in cuts}
    assert len(versions) == 1, f"pipeline versions differ: {versions}"
    exp_a, ra_a, dec_a, _, trunc_a = cuts[0]
    calib = await calib_cache.ensure_calib(DETECTOR, trunc_a.version, exp_a, ra_a, dec_a)
    assert calib is not None and calib.exists()
    assert str(get_settings().cache_dir) in str(calib)

    worst = 0.0
    for exp, ra, dec, full, trunc in cuts:
        # evaluate at the target and at a few other sky positions inside the cutout
        for ddx, ddy in [(0.0, 0.0), (0.004, 0.0), (-0.004, 0.003), (0.0, -0.004)]:
            tra = EPS_IND_B[0] + ddx / math.cos(math.radians(EPS_IND_B[1]))
            tdec = EPS_IND_B[1] + ddy
            lam_full, bw_full = _lambda_from_full(full, tra, tdec)
            lam_tr, bw_tr, src = calib_cache.wavelength_at(trunc, tra, tdec, calib, exp=exp)
            assert src == "wcs_wave"
            assert 4.42 <= lam_tr <= 5.0 and 4.42 <= lam_full <= 5.0
            worst = max(worst, abs(lam_full - lam_tr))
            assert lam_tr == pytest.approx(lam_full, abs=TOL_UM), (exp.obs_id, ddx, ddy)
            assert bw_tr == pytest.approx(bw_full, abs=TOL_UM)
    print(f"max |lambda_full - lambda_truncated+calib| = {worst * 1000:.4f} nm")

    # informational: different exposures place the target at different wavelengths (this is what makes the test non-trivial)
    l_a = _lambda_from_full(cuts[0][3], *EPS_IND_B)[0]
    l_b = _lambda_from_full(cuts[1][3], *EPS_IND_B)[0]
    print(f"lambda at target: exposure A {l_a:.4f} um, exposure B {l_b:.4f} um")


async def test_epsf_loadable_from_calib(tmp_path):
    exps, _ = await irsa_sia.query_exposures(*EPS_IND_B, ["spherex_dr1"])
    exp = next(e for e in exps if e.detector == DETECTOR)
    path = await cutouts.fetch_cutout(exp, *EPS_IND_B, SIZE_DEG)
    cut = cutouts.load_cutout(path, exp)
    calib = await calib_cache.ensure_calib(DETECTOR, cut.version, exp, *EPS_IND_B)
    assert calib is not None
    xd, yd = calib_cache.detector_xy(cut, cut.image.shape[1] / 2, cut.image.shape[0] / 2)
    epsf = calib_cache.load_epsf(calib, xd, yd)
    assert epsf is not None and epsf.ndim == 2
    assert epsf.sum() == pytest.approx(1.0)
    assert calib_cache.epsf_oversampling(calib) >= 1
