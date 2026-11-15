import numpy as np

from app import models
from app.science import spectrum


def pt(obs, visit, det, wl, flux, err=1.0, sat=False, outlier=False):
    return models.PhotPoint(obs_id=obs, visit_id=visit, detector=det, mjd=60900.0, wavelength_um=wl,
                            bandwidth_um=0.03, flux_ujy=flux, flux_err_ujy=err, saturated=sat,
                            outlier=outlier, x=0.0, y=0.0)


def test_channel_grid_102():
    c, d = spectrum.channel_grid()
    assert len(c) == 102 and len(d) == 102
    assert all(d.count(k) == 17 for k in range(1, 7))
    assert all(b > a for a, b in zip(c, c[1:]))
    r = np.diff(np.log(c[:17]))
    assert np.allclose(r, r[0])          # equal log-lambda steps within a detector
    assert 0.75 < c[0] < 0.8 and 4.9 < c[-1] < 5.0


def test_bins_weighted_mean_gaps_and_saturation():
    c, d = spectrum.channel_grid()
    k1, k2 = 3, 40          # a D1 channel and a D3 channel
    pts = [
        pt("a", "v0", 1, c[k1], 10.0, 1.0),
        pt("b", "v0", 1, c[k1], 20.0, 1.0),
        pt("c", "v0", d[k2], c[k2], 30.0, 1.0, sat=True),
        pt("d", "v0", d[k2], c[k2], 50.0, 1.0, sat=True),
        pt("e", "v0", 1, c[k1], 999.0, 1.0, outlier=True),
        pt("f", "v1", 1, c[k1], 5.0, 2.0),
    ]
    sp = spectrum.build_spectrum(pts)
    assert len(sp.channels_um) == 102 and len(sp.channel_detector) == 102
    assert [v.visit_id for v in sp.visits] == ["v0", "v1"]
    v0 = sp.visits[0].points
    assert len(v0) == 102
    assert abs(v0[k1].flux_ujy - 15.0) < 1e-9 and v0[k1].n == 2
    assert abs(v0[k1].flux_err_ujy - 1 / np.sqrt(2)) < 1e-9
    assert v0[k2].saturated and v0[k2].flux_ujy == 50.0 and v0[k2].flux_err_ujy is None
    gaps = [p for i, p in enumerate(v0) if i not in (k1, k2)]
    assert all(p.flux_ujy is None and p.n == 0 for p in gaps)
    assert sp.visits[1].points[k1].flux_ujy == 5.0
    assert sp.features and all("not a detection claim" in f.note for f in sp.features)
    assert sp.wavelength_source == "wcs_wave"


def test_point_outside_detector_range_dropped():
    sp = spectrum.build_spectrum([pt("a", "v0", 1, 2.0, 10.0)])   # 2.0 um is not in D1
    assert all(p.flux_ujy is None for p in sp.visits[0].points)
