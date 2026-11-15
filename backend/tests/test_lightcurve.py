from app import models
from app.science import lightcurve


def pt(i, visit, det, wl, flux, err=1.0, mjd=60900.0, sat=False):
    return models.PhotPoint(obs_id=f"o{i}", visit_id=visit, detector=det, mjd=mjd, wavelength_um=wl,
                            bandwidth_um=0.03, flux_ujy=flux, flux_err_ujy=err, saturated=sat, x=0.0, y=0.0)


VISITS = [models.Visit(id="v0", mjd_start=60900, mjd_end=60905, mjd_mean=60902, date_label="a",
                       collection="spherex_qr", n_exposures=8, detectors=[2, 3]),
          models.Visit(id="v1", mjd_start=61100, mjd_end=61105, mjd_mean=61102, date_label="b",
                       collection="spherex_qr", n_exposures=8, detectors=[2, 3])]


def test_outlier_flagged_and_excluded_from_chi2():
    # visits interleave in wavelength (as SPHEREx sampling does); one isolated glitch in v1
    vals = [100, 101, 99, 100.5, 99.5, 100, 101, 99, 160]
    wls = [3.00, 3.02, 3.04, 3.06, 3.08, 3.01, 3.03, 3.07, 3.05]
    phot = [pt(i, "v0" if i < 5 else "v1", 4, wl, v, mjd=60900.0 + 40 * i)
            for i, (v, wl) in enumerate(zip(vals, wls))]
    lc, out = lightcurve.metrics(phot, VISITS)
    assert [p.outlier for p in out] == [False] * 8 + [True]
    m = [x for x in lc.metrics if x.detector == 4][0]
    assert m.n == 8
    assert m.chi2_red < 2.0 and not m.significant


def test_coherent_variability_across_two_detectors():
    phot = []
    i = 0
    for det, wls in ((2, [1.2, 1.25, 1.3, 1.35]), (3, [1.8, 1.9, 2.0, 2.1]), (4, [3.0, 3.1, 3.2, 3.3])):
        for visit, mjd, base in (("v0", 60900.0, 100.0), ("v1", 61100.0, 60.0 if det != 4 else 100.0)):
            for j, wl in enumerate(wls):
                phot.append(pt(i, visit, det, wl, base + (0.5 if j == 1 else -0.5 if j == 2 else 0.0),
                               mjd=mjd + j))
                i += 1
    lc, out = lightcurve.metrics(phot, VISITS)
    by = {m.detector: m for m in lc.metrics}
    assert by[2].significant and by[3].significant and not by[4].significant
    assert lc.coherent_detectors == 2
    assert lc.reference_visit == "v0"
    assert "no period" in lc.period_note.lower()
    v1 = [p for p in out if p.visit_id == "v1" and p.detector == 2]
    assert all(abs(p.rel_flux - 0.6) < 0.02 for p in v1)


def test_saturated_points_excluded():
    phot = [pt(0, "v0", 2, 1.2, 1000.0, sat=True), pt(1, "v0", 2, 1.2, 10.0),
            pt(2, "v1", 2, 1.2, 10.0, mjd=61100.0)]
    lc, out = lightcurve.metrics(phot, VISITS)
    assert lc.metrics[0].n == 2
    assert lc.reference_visit is None      # < 3 usable points in any visit
    assert all(p.rel_flux is None for p in out)


def test_steep_spectrum_sampled_at_different_wavelengths_is_not_variable():
    """Regression: a constant source with a steep in-detector spectrum (brown-dwarf-like, ×16 over D1) whose visits
    sample different wavelengths must not look variable (live Eps Ind B gave χ²_red ≈ 1000 before the fix)."""
    import math
    spec = lambda wl: 1000.0 * math.exp(12.0 * (wl - 0.85))  # noqa: E731
    phot, i = [], 0
    for visit, mjd, wls in (("v0", 60900.0, [0.76, 0.84, 0.95, 1.05]), ("v1", 61100.0, [0.80, 0.90, 1.00, 1.08])):
        for wl in wls:
            f = spec(wl)
            phot.append(pt(i, visit, 1, wl, f, err=0.01 * f, mjd=mjd))
            i += 1
    lc, out = lightcurve.metrics(phot, VISITS)
    m = lc.metrics[0]
    assert not m.significant and m.chi2_red < 2.0 and abs(m.frac_amp) < 0.02
    assert not any(p.outlier for p in out)


def test_grey_visit_offset_on_steep_spectrum_is_detected():
    import math
    spec = lambda wl: 1000.0 * math.exp(12.0 * (wl - 0.85))  # noqa: E731
    phot, i = [], 0
    for visit, mjd, scale, wls in (("v0", 60900.0, 1.0, [0.76, 0.84, 0.95, 1.05]),
                                   ("v1", 61100.0, 0.7, [0.80, 0.90, 1.00, 1.08])):
        for wl in wls:
            f = scale * spec(wl)
            phot.append(pt(i, visit, 1, wl, f, err=0.01 * f, mjd=mjd))
            i += 1
    lc, _ = lightcurve.metrics(phot, VISITS)
    m = lc.metrics[0]
    assert m.significant and abs(m.frac_amp - (1 / 0.7 - 1)) < 0.03
