import json
import math

import httpx
import pytest

from app.services import crossmatch as cx

DT10 = 10.0 * 365.25
MJD_2026 = cx.GAIA_REF_MJD + DT10          # ten years after Gaia's reference epoch

# Barnard's-Star-like Gaia row (epoch J2016.0)
RA16, DEC16 = 269.45, 4.60
GAIA_CSV = (
    "source_id,ra,dec,pmra,pmdec,parallax,phot_g_mean_mag,phot_variable_flag\n"
    f"4472832130942575872,{RA16},{DEC16},-801.6,10362.4,546.98,9.51,NOT_AVAILABLE\n"
    "111,269.4502,4.6001,,,,16.80,\n"                                  # no PM / parallax
    "222,270.5,5.9,1.0,1.0,1.0,12.0,VARIABLE\n"                         # far away
)


def at_epoch():
    """Barnard's position propagated by hand 10 yr (independent of the code under test)."""
    dec = DEC16 + 10362.4 * 10 / 3.6e6
    ra = RA16 + (-801.6 * 10 / 3.6e6) / math.cos(math.radians(DEC16))
    return ra, dec


def test_gaia_is_propagated_before_matching():
    ra, dec = at_epoch()
    m = cx.parse_gaia_csv(GAIA_CSV, ra, dec, 3.0, MJD_2026)
    assert [x.id for x in m] == ["Gaia DR3 4472832130942575872"]
    assert m[0].sep_arcsec < 0.05 and m[0].epoch_propagated is True
    assert m[0].mag == 9.51 and m[0].mag_band == "G"
    assert m[0].pm_dec == 10362.4 and m[0].parallax == 546.98
    assert m[0].variable_flag == "NOT_AVAILABLE"
    assert m[0].dec == pytest.approx(dec, abs=1e-6)


def test_gaia_without_epoch_does_not_propagate():
    ra, dec = at_epoch()
    assert cx.parse_gaia_csv(GAIA_CSV, ra, dec, 3.0, None) == []      # 100+ arcsec away at J2016.0
    m = cx.parse_gaia_csv(GAIA_CSV, RA16, DEC16, 3.0, None)
    assert m[0].epoch_propagated is False and m[0].sep_arcsec == 0.0


def test_gaia_missing_pm_and_sorting_and_radius():
    m = cx.parse_gaia_csv(GAIA_CSV, 269.4502, 4.6001, 400.0, MJD_2026)
    seps = [x.sep_arcsec for x in m]
    assert seps == sorted(seps)
    row = next(x for x in m if x.id.endswith("111"))
    assert row.pm_ra is None and row.epoch_propagated is False and row.sep_arcsec == 0.0
    assert not any(x.id.endswith("222") for x in m)                    # > 400 arcsec


def test_gaia_mag_range_and_limit():
    m = cx.parse_gaia_csv(GAIA_CSV, RA16, DEC16, 36000.0, None, mag_range=(10.0, 16.0))
    assert [x.id[-3:] for x in m] == ["222"]
    m2 = cx.parse_gaia_csv(GAIA_CSV, RA16, DEC16, 36000.0, None, limit=1)
    assert len(m2) == 1


def test_bad_csv_raises_value_error():
    with pytest.raises(ValueError):
        cx.parse_gaia_csv("<html>Service unavailable</html>", 1, 1, 3, None)
    with pytest.raises(ValueError):
        cx.parse_gaia_csv("", 1, 1, 3, None)
    assert cx.parse_gaia_csv("source_id,ra,dec,pmra,pmdec\n", 1, 1, 3, None) == []   # empty result is valid


SIMBAD_CSV = (
    '"main_id","otype","ra","dec","pmra","pmdec","plx_value"\n'
    '"* Bernard\'s star","PM*",269.45208,4.69336,-801.551,10362.394,546.9759\n'
    '"UCAC4 474-068227","*",269.4565426257566,4.706951530262222,,,\n'
)


def test_simbad_parse_j2000_propagation():
    # query at the 2026-epoch position of Barnard's star (26 yr after J2000)
    mjd = cx.MJD_J2000 + 26.0 * 365.25
    ra = 269.45208 + (-801.551 * 26 / 3.6e6) / math.cos(math.radians(4.69336))
    dec = 4.69336 + 10362.394 * 26 / 3.6e6
    m = cx.parse_simbad_csv(SIMBAD_CSV, ra, dec, 3.0, mjd)
    assert len(m) == 1 and m[0].id == "* Bernard's star" and m[0].otype == "PM*"
    assert m[0].sep_arcsec < 0.05 and m[0].epoch_propagated and m[0].parallax == pytest.approx(546.9759)
    both = cx.parse_simbad_csv(SIMBAD_CSV, 269.4565, 4.7069, 5.0, None)
    assert both[0].id == "UCAC4 474-068227" and both[0].pm_ra is None


def test_variable_otype_helper_set():
    assert "Mi*" in cx.VARIABLE_OTYPES and "PM*" not in cx.VARIABLE_OTYPES


CATWISE_CSV = (
    "source_name,ra,dec,pmra,pmdec,w1mpro,w2mpro\n"
    "J080355.15-071451.1,133.81891,-7.24705,-8.1237,0.6732,17.5,13.9\n"
    "J000000.00+000000.0,133.8189,-7.2470,,,16.0,\n"
)


def test_catwise_pm_converted_from_arcsec_and_propagated():
    mjd = cx.CATWISE_REF_MJD + 11.0 * 365.25
    ra = 133.81891 + (-8123.7 * 11 / 3.6e6) / math.cos(math.radians(-7.24705))
    dec = -7.24705 + 673.2 * 11 / 3.6e6
    m = cx.parse_catwise_csv(CATWISE_CSV, ra, dec, 5.0, mjd)
    assert m[0].id == "J080355.15-071451.1" and m[0].sep_arcsec < 0.05
    assert m[0].pm_ra == pytest.approx(-8123.7) and m[0].pm_dec == pytest.approx(673.2)
    assert m[0].mag == 13.9 and m[0].mag_band == "W2"


def test_catwise_falls_back_to_w1():
    m = cx.parse_catwise_csv(CATWISE_CSV, 133.8189, -7.2470, 1.0, None)
    assert m[0].mag_band == "W1" and m[0].mag == 16.0


SKYBOT = [{"Num": 162134, "Name": "1998 TJ24", "RA (hms)": "12 00 11.1435", "DEC (dms)": "+10 00 00.00",
           "Class": "MB>Inner", "VMag (mag)": 20.9, "Err (arcsec)": 0.5, "d (arcsec)": 205.878}]
SK_RA = (12 + 11.1435 / 3600) * 15


def test_skybot_list_json():
    m = cx.parse_skybot_json(json.dumps(SKYBOT), SK_RA, 10.0, 10.0)
    assert len(m) == 1
    x = m[0]
    assert x.id == "(162134) 1998 TJ24" and x.class_ == "MB>Inner" and x.mag == 20.9 and x.mag_band == "V"
    assert x.sep_arcsec < 0.01 and x.epoch_propagated
    assert x.ra == pytest.approx(SK_RA, abs=1e-6) and x.dec == pytest.approx(10.0)


def test_skybot_data_wrapper_degrees_and_filtering():
    row = {"Name": "Ceres", "RA (deg)": SK_RA + 8 / 3600, "DEC (deg)": 10.0, "Class": "MB>MiddleMain", "V": 8.9}
    far = {"Name": "Vesta", "RA (deg)": SK_RA + 1.0, "DEC (deg)": 10.0}
    m = cx.parse_skybot_json(json.dumps({"data": [row, far]}), SK_RA, 10.0, 10.0)
    assert [x.id for x in m] == ["Ceres"] and m[0].sep_arcsec == pytest.approx(8 * math.cos(math.radians(10)), abs=0.05)
    # positional error widens the acceptance (radius + 3 x err)
    wide = dict(row, **{"Err (arcsec)": 2.0, "RA (deg)": SK_RA + 14 / 3600})
    assert len(cx.parse_skybot_json(json.dumps([wide]), SK_RA, 10.0, 10.0)) == 1


def test_skybot_empty_and_bad():
    assert cx.parse_skybot_json("[]", 1, 1, 10) == []
    assert cx.parse_skybot_json("No solar system object was found in the FOV", 1, 1, 10) == []
    with pytest.raises(ValueError):
        cx.parse_skybot_json("<html>oops</html>", 1, 1, 10)


def test_helpers():
    assert cx.angular_sep_arcsec(10, 0, 10, 1 / 3600) == pytest.approx(1.0)
    ra, dec = cx.propagate_linear(0.0, 60.0, 1000.0, 500.0, 2.0)
    assert dec == pytest.approx(60 + 500 * 2 / 3.6e6)
    assert ra == pytest.approx(1000 * 2 / 3.6e6 / 0.5, rel=1e-6)
    assert cx._search_radius(3.0, cx.GAIA_REF_MJD, MJD_2026, 180.0) == pytest.approx(3.0 + 10.5 * 10, rel=1e-3)
    assert cx._search_radius(3.0, cx.GAIA_REF_MJD, cx.GAIA_REF_MJD + 100 * 365.25, 180.0) == 180.0
    assert cx._search_radius(3.0, cx.GAIA_REF_MJD, None, 180.0) == 3.0


# ---------------- network layer with a fake http.fetch (no real network) ----------------
class FakeResp:
    def __init__(self, text):
        self.text = text


@pytest.fixture
def no_cache(monkeypatch):
    monkeypatch.setattr(cx.cache, "read_json", lambda *a, **k: None)
    monkeypatch.setattr(cx.cache, "write_json", lambda *a, **k: None)


async def test_gaia_cone_ok_and_failure_modes(monkeypatch, no_cache):
    async def ok(method, url, **kw):
        assert "gaiadr3.gaia_source" in kw["params"]["QUERY"]
        return FakeResp(GAIA_CSV)
    monkeypatch.setattr(cx.http, "fetch", ok)
    res = await cx.gaia_cone(RA16, DEC16, 0.5, None)
    assert res.status == "ok" and len(res.matches) == 1

    async def timeout(method, url, **kw):
        raise httpx.ConnectTimeout("t")
    monkeypatch.setattr(cx.http, "fetch", timeout)
    assert (await cx.gaia_cone(RA16, DEC16, 3.0, None)).status == "unavailable"

    async def garbage(method, url, **kw):
        return FakeResp("<html>nope</html>")
    monkeypatch.setattr(cx.http, "fetch", garbage)
    assert (await cx.gaia_cone(RA16, DEC16, 3.0, None)).status == "error"
    assert await cx.bright_stars(RA16, DEC16) is None
    assert await cx.gaia_field(RA16, DEC16, 60.0, 60000.0) == []


async def test_simbad_fails_over_to_second_mirror(monkeypatch, no_cache):
    urls = []

    async def fetch(method, url, **kw):
        urls.append(url)
        if len(urls) == 1:
            raise httpx.ConnectError("down")
        return FakeResp(SIMBAD_CSV)
    monkeypatch.setattr(cx.http, "fetch", fetch)
    res = await cx.simbad_cone(269.4565, 4.7069, 5.0, None)
    assert res.status == "ok" and len(urls) == 2 and urls[0] != urls[1]


async def test_crossmatch_all_never_raises(monkeypatch, no_cache):
    async def boom(method, url, **kw):
        raise RuntimeError("boom")
    monkeypatch.setattr(cx.http, "fetch", boom)
    out = await cx.crossmatch_all(10.0, 10.0, 3.0, 60000.0)
    assert {out.gaia.status, out.simbad.status, out.catwise.status, out.skybot.status} <= {"error", "unavailable"}
