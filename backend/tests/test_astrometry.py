import math

import numpy as np
from astropy.wcs import WCS
from scipy.special import erf

from app import models
from app.science import astrometry, ephemeris

PIX = 6.15
EPS_IND_B = models.Target(name="Eps Ind B", ra=331.04415, dec=-56.78284, pm_ra=3982.0, pm_dec=-2466.8,
                          parallax=270.66, ref_epoch=2000.0)


def make_wcs(nx, ny, ra=150.0, dec=2.0):
    w = WCS(naxis=2)
    w.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    w.wcs.crval = [ra, dec]
    w.wcs.crpix = [(nx + 1) / 2, (ny + 1) / 2]
    w.wcs.cdelt = [-PIX / 3600, PIX / 3600]
    return w


def star(n, x0, y0, amp, fwhm_px=2.5):
    """Pixel-integrated Gaussian with peak value ~amp."""
    sigma = fwhm_px / 2.3548200450309493
    e = np.arange(n + 1) - 0.5

    def cdf(c):
        return 0.5 * (1 + erf((e - c) / (sigma * math.sqrt(2))))

    return amp * np.outer(np.diff(cdf(y0)), np.diff(cdf(x0))) * 2 * math.pi * sigma ** 2


def synth_measured(mjds, target, noise=0.0, err=0.05, seed=1, snr=50.0):
    rng = np.random.default_rng(seed)
    tr = ephemeris.predict_track(target, list(mjds))
    out = []
    for i, (m, (ra, dec)) in enumerate(zip(mjds, tr)):
        dra = rng.normal(0, noise) / 3600 / math.cos(math.radians(dec)) if noise else 0.0
        ddec = rng.normal(0, noise) / 3600 if noise else 0.0
        out.append(models.AstrometryMeasured(visit_id=f"v{i}", mjd=float(m), ra=ra + dra, dec=dec + ddec,
                                             err_arcsec=err, snr=snr, detector=5))
    return out


def test_centroid_recovers_position_and_crowding():
    n = 21
    w = make_wcs(n, n)
    img = star(n, 10.3, 9.6, 100.0)
    var = np.full((n, n), 1.0)
    ra, dec = w.all_pix2world(10, 10, 0)
    c = astrometry.centroid(img, var, w, float(ra), float(dec), 2.5)
    assert c is not None
    assert abs(c.x - 10.3) < 0.1 and abs(c.y - 9.6) < 0.1
    assert c.snr > 10 and not c.crowded and not c.saturated
    assert c.err_arcsec >= 0.3
    img2 = img + star(n, 14.0, 10.0, 60.0)
    c2 = astrometry.centroid(img2, var, w, float(ra), float(dec), 2.5)
    assert c2 is not None and c2.crowded


def test_centroid_rejects_low_snr_nan_and_edge():
    n = 21
    w = make_wcs(n, n)
    var = np.full((n, n), 1.0)
    ra, dec = w.all_pix2world(10, 10, 0)
    assert astrometry.centroid(star(n, 10, 10, 0.2), var, w, float(ra), float(dec), 2.5) is None
    img = star(n, 10, 10, 100.0)
    img[8:13, 8:13] = np.nan
    assert astrometry.centroid(img, var, w, float(ra), float(dec), 2.5) is None
    ra2, dec2 = w.all_pix2world(0, 0, 0)
    assert astrometry.centroid(star(n, 10, 10, 100.0), var, w, float(ra2), float(dec2), 2.5) is None


def test_fit_pm_recovers_injected_pm_fixed_parallax():
    meas = synth_measured([60900.0, 61000.0, 61120.0], EPS_IND_B)
    fit = astrometry.fit_pm(meas, EPS_IND_B)
    assert fit is not None and fit.parallax_mode == "fixed_catalog"
    # linear fit vs rigorous (curved-sky, 26 yr from J2000) synthetic track: few-mas/yr model error, << fit error
    assert abs(fit.pm_ra - 3982.0) < 10.0 and abs(fit.pm_dec + 2466.8) < 10.0
    assert fit.n_points == 3 and 0.5 < fit.baseline_yr < 0.7


def test_fit_pm_noisy_within_errors():
    meas = synth_measured([60900.0 + 60 * i for i in range(6)], EPS_IND_B, noise=0.02, err=0.03, seed=3)
    fit = astrometry.fit_pm(meas, EPS_IND_B)
    assert fit is not None
    assert abs(fit.pm_ra - 3982.0) < 5 * fit.pm_ra_err
    assert abs(fit.pm_dec + 2466.8) < 5 * fit.pm_dec_err


def test_fit_pm_requires_baseline_and_quality():
    meas = synth_measured([60900.0, 60950.0], EPS_IND_B)       # 0.14 yr
    assert astrometry.fit_pm(meas, EPS_IND_B) is None
    meas = synth_measured([60900.0, 61100.0], EPS_IND_B)
    meas[0].crowded = True
    assert astrometry.fit_pm(meas, EPS_IND_B) is None
    meas = synth_measured([60900.0, 61100.0], EPS_IND_B, snr=6.0)
    assert astrometry.fit_pm(meas, EPS_IND_B) is None


def test_free_parallax_recovered():
    meas = synth_measured([60900.0 + 70 * i for i in range(8)], EPS_IND_B)   # 1.34 yr, 8 epochs
    fit = astrometry.fit_pm(meas, EPS_IND_B)
    assert fit.parallax_mode == "fitted"
    assert abs(fit.parallax - 270.66) < 5.0
    assert fit.parallax_err is not None
    assert abs(fit.pm_ra - 3982.0) < 5.0 and abs(fit.pm_dec + 2466.8) < 5.0


def test_no_catalog_parallax_mode_none():
    t = models.Target(ra=10.0, dec=10.0, pm_ra=100.0, pm_dec=50.0, ref_epoch=2000.0)
    fit = astrometry.fit_pm(synth_measured([60900.0, 61000.0, 61100.0], t), t)
    assert fit.parallax_mode == "none" and fit.parallax is None
    assert abs(fit.pm_ra - 100.0) < 1.0


def test_residuals_zero_on_predicted_track_and_offset_recovered():
    meas = synth_measured([60900.0, 61100.0], EPS_IND_B)
    res = astrometry.residuals(meas, EPS_IND_B)
    assert all(abs(r.resid_ra_arcsec) < 1e-6 and abs(r.resid_dec_arcsec) < 1e-6 for r in res)
    meas[0].dec += 1.0 / 3600
    res = astrometry.residuals(meas, EPS_IND_B)
    assert abs(res[0].resid_dec_arcsec - 1.0) < 1e-3


def test_registration_check():
    n = 61
    w = make_wcs(n, n)
    pos = [(10.2, 12.1), (45.7, 15.3), (20.4, 47.9), (48.1, 49.6), (30.5, 30.2)]
    img = sum(star(n, x, y, 100.0) for x, y in pos)
    var = np.full((n, n), 1.0)
    stars = []
    for i, (x, y) in enumerate(pos):
        ra, dec = w.all_pix2world(x, y, 0)
        stars.append(models.CatalogMatch(id=str(i), ra=float(ra), dec=float(dec), sep_arcsec=0.0))
    reg = astrometry.registration_check(img, w, stars, 2.5, variance=var)
    assert reg is not None and reg.n_stars >= 3
    assert reg.rms_arcsec < 1.5 and reg.median_offset_arcsec < 1.0
    assert astrometry.registration_check(img, w, stars[:2], 2.5, variance=var) is None
