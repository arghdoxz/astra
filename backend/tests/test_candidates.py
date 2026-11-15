import numpy as np
import pytest
from astropy.wcs import WCS

from app.core_types import DiffContext, DiffResult, GridSpec
from app.science.candidates import find_candidates

N = 64
DT_YR = 1.0
MJD_A = 60000.0
MJD_B = MJD_A + 365.25 * DT_YR


def make_grid():
    w = WCS(naxis=2)
    w.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    w.wcs.crval = [150.0, 2.0]
    w.wcs.crpix = [(N + 1) / 2, (N + 1) / 2]
    w.wcs.cdelt = [-6.15 / 3600, 6.15 / 3600]          # north up, east left (x increases west)
    return GridSpec(wcs=w, shape=(N, N), ra=150.0, dec=2.0)


def make_ctx(det, z, contam=None, good=None, va="v0", vb="v1"):
    return DiffContext(
        visit_a=va, visit_b=vb, detector=det, mjd_a=MJD_A, mjd_b=MJD_B,
        diff=DiffResult(D=np.zeros_like(z), Z=z, method="simple"),
        contam=np.zeros(z.shape, bool) if contam is None else contam,
        good=np.ones(z.shape, bool) if good is None else good)


def dipole_z(z):
    z[15, 23] = 9.0      # positive peak (where the source is in epoch b)
    z[15, 20] = -8.0     # negative peak (where it was in epoch a)
    return z


def test_dipole_recurs_in_two_detectors_and_gives_motion():
    grid = make_grid()
    ctxs = [make_ctx(1, dipole_z(np.zeros((N, N)))), make_ctx(2, dipole_z(np.zeros((N, N))))]
    cands = find_candidates(ctxs, grid, max_pm_mas_yr=30000)
    assert len(cands) == 1
    c = cands[0]
    assert c.id == "c0" and c.kind == "dipole"
    assert c.detectors == [1, 2] and c.recurrence == 2
    assert c.peak_z == pytest.approx(9.0)
    assert not any("single detector" in r for r in c.rejection_reasons)
    # +x is west: source moved 3 px west in 1 yr -> mu_alpha* negative; no dec motion
    assert c.pm_ra == pytest.approx(-3 * 6.15 * 1000, rel=1e-6)
    assert c.pm_dec == pytest.approx(0.0, abs=1e-6)
    assert c.x == pytest.approx(21.5) and c.y == pytest.approx(15.0)
    assert 149.9 < c.ra < 150.1 and 1.9 < c.dec < 2.1
    assert c.n_good_pixels == 25


def test_monopole_single_detector_is_low_confidence_not_deleted():
    grid = make_grid()
    z = np.zeros((N, N))
    z[40, 45] = 7.0
    cands = find_candidates([make_ctx(1, z)], grid)
    assert len(cands) == 1 and cands[0].kind == "monopole"
    assert cands[0].recurrence == 1 and cands[0].pm_ra is None
    assert "low-confidence: single detector & pair" in cands[0].rejection_reasons


def test_contamination_and_bad_pixels_are_recorded():
    grid = make_grid()
    z = np.zeros((N, N))
    z[10, 50] = -6.0
    contam = np.zeros((N, N), bool)
    contam[9:12, 51:53] = True                      # within 3 px of the peak
    good = np.ones((N, N), bool)
    good[8:13, 48:53] = False                       # the whole 5x5 box is bad
    cands = find_candidates([make_ctx(1, z, contam=contam, good=good)], grid)
    c = cands[0]
    assert c.contamination_near and c.n_good_pixels < 5
    assert any("contamination" in r for r in c.rejection_reasons)
    assert any("good pixels" in r for r in c.rejection_reasons)


def test_distant_contamination_is_ignored():
    grid = make_grid()
    z = np.zeros((N, N))
    z[10, 50] = 6.0
    contam = np.zeros((N, N), bool)
    contam[40:45, 5:10] = True
    c = find_candidates([make_ctx(1, z, contam=contam)], grid)[0]
    assert c.contamination_near == []


def test_target_position_is_marked_not_removed():
    grid = make_grid()
    z = np.zeros((N, N))
    z[31, 31] = 9.0                                 # crpix-1 = 31.5 -> within 2 px
    c = find_candidates([make_ctx(1, z)], grid)[0]
    assert "at target position (see target evidence)" in c.rejection_reasons


def test_below_threshold_and_nan_give_nothing():
    grid = make_grid()
    z = np.zeros((N, N))
    z[20, 20] = 4.9
    z[30, 30] = np.nan
    assert find_candidates([make_ctx(1, z)], grid) == []


def test_recurrence_across_visit_pairs_and_sorting_and_cap():
    grid = make_grid()
    z1 = np.zeros((N, N)); z1[20, 20] = 6.0
    z2 = np.zeros((N, N)); z2[21, 20] = 7.0         # 1 px away -> same cluster, different visit pair
    cands = find_candidates([make_ctx(1, z1, va="v0", vb="v1"), make_ctx(1, z2, va="v1", vb="v2")], grid)
    assert len(cands) == 1 and cands[0].recurrence == 2
    assert cands[0].visit_pairs == [("v0", "v1"), ("v1", "v2")]

    many = np.zeros((N, N))
    k = 0
    for y in range(4, N - 4, 8):
        for x in range(4, N - 4, 8):
            many[y, x] = 5.5 + 0.01 * k
            k += 1
    out = find_candidates([make_ctx(1, many)], grid)
    assert len(out) == 25
    assert [c.id for c in out][:3] == ["c0", "c1", "c2"]
    assert all(out[i].peak_z >= out[i + 1].peak_z for i in range(len(out) - 1))
