import math

import numpy as np

from app import models
from app.science import ephemeris

BARNARD = models.Target(name="Barnard's Star", ra=269.45208, dec=4.69336, pm_ra=-801.6, pm_dec=10362.4,
                        parallax=546.98, ref_epoch=2000.0)
WISE0855 = models.Target(name="WISE 0855", ra=133.81891, dec=-7.24705, pm_ra=-8123.7, pm_dec=673.2,
                         parallax=439.0, ref_epoch=2000.0)


def test_barnard_parallax_ellipse_amplitude():
    mjds = np.linspace(60900.0, 60900.0 + 365.25, 366)
    pf = ephemeris.parallax_factors(BARNARD.ra, BARNARD.dec, mjds)
    assert pf.shape == (366, 2)
    off_arcsec = pf * BARNARD.parallax / 1000.0
    c = off_arcsec.mean(axis=0)
    amp = np.hypot(*(off_arcsec - c).T).max()
    assert abs(amp - 0.55) < 0.05
    assert off_arcsec[:, 0].max() - off_arcsec[:, 0].min() > 0.9   # RA range ~ 2 x 0.547


def test_parallax_only_track_has_no_aberration():
    t = models.Target(ra=269.45208, dec=4.69336, parallax=546.98, ref_epoch=2000.0)
    tr = ephemeris.predict_track(t, [60900.0, 61000.0, 61100.0])
    for ra, dec in tr:
        d = math.hypot((ra - t.ra) * math.cos(math.radians(t.dec)), dec - t.dec) * 3600
        assert d < 0.7          # parallax only (aberration would be ~20 arcsec)


def test_wise0855_j2000_to_2026_offset():
    ra, dec = ephemeris.predict_track(WISE0855, [61041.0])[0]   # 2026-01-01
    d = math.hypot((ra - WISE0855.ra) * math.cos(math.radians(WISE0855.dec)), dec - WISE0855.dec) * 3600
    assert abs(d - 8.151 * 26.0) < 1.5


def test_no_motion_returns_fixed_position():
    t = models.Target(ra=10.0, dec=-20.0)
    assert ephemeris.predict_track(t, [60000.0, 61000.0]) == [(10.0, -20.0), (10.0, -20.0)]


def test_propagate_matches_predict_track():
    a = ephemeris.propagate(WISE0855.ra, WISE0855.dec, -8123.7, 673.2, 439.0, 2000.0, 61041.0)
    b = ephemeris.predict_track(WISE0855, [61041.0])[0]
    assert abs(a[0] - b[0]) < 1e-9 and abs(a[1] - b[1]) < 1e-9
