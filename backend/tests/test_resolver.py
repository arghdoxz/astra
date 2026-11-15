"""Offline tests for the target resolver (no network: built-ins and the coordinate parser only)."""
from __future__ import annotations

import math

import pytest

from app.services import resolver
from app.services.resolver import BUILTIN_TARGETS, match_builtin, parse_coordinates

WISE_RA, WISE_DEC = 133.79513, -7.24515  # challenge text: 08h55m10.831s -07d14m42.53s (~2010 epoch)


def _close(got, want, tol=1e-3):
    assert got is not None
    assert got[0] == pytest.approx(want[0], abs=tol)
    assert got[1] == pytest.approx(want[1], abs=tol)


@pytest.mark.parametrize("q,want", [
    ("133.795 -7.245", (133.795, -7.245)),
    ("133.795, -7.245", (133.795, -7.245)),
    ("  269.452   +4.6934 ", (269.452, 4.6934)),
    ("08 55 10.83 -07 14 42.5", (133.79513, -7.24514)),
    ("08h55m10.831s -7d14m42.53s", (WISE_RA, WISE_DEC)),
    ("08:55:10.8 -07:14:42", (133.795, -7.245)),
    ("08h55m10.831s −7d14m42.53s", (WISE_RA, WISE_DEC)),  # unicode minus
    ("J085510.83-071442.5", (133.79513, -7.24514)),
    ("22 04 10.5 +56 46 58", (331.04375, 56.78278)),
])
def test_parse_coordinates_ok(q, want):
    _close(parse_coordinates(q), want)


def test_negative_zero_degrees_keeps_sign():
    ra, dec = parse_coordinates("10 00 00 -00 30 00")
    assert dec == pytest.approx(-0.5)
    assert ra == pytest.approx(150.0)


@pytest.mark.parametrize("q", [
    "", "barnard", "Barnard's star", "gj 699", "eps ind b", "WISE 0855-0714", "R Dra",
    "400 10", "100 95", "25 00 00 +10 00 00", "08 61 00 +10 00 00", "1 2 3", "-5 10",
    "x" * 200,
])
def test_parse_coordinates_rejects(q):
    assert parse_coordinates(q) is None


def test_builtin_catalogue_shape():
    assert [t["slug"] for t in BUILTIN_TARGETS] == ["barnard", "eps-ind-b", "wise-0855", "rw-aur", "r-dra"]
    for t in BUILTIN_TARGETS:
        for k in ("name", "aliases", "ra", "dec", "pm_ra", "pm_dec", "parallax", "ref_epoch", "otype",
                  "classification", "background", "capabilities", "default_fov_arcmin"):
            assert k in t, (t["slug"], k)
        assert t["ref_epoch"] == 2000.0 and t["default_fov_arcmin"] == 3
        assert 0 <= t["ra"] < 360 and -90 <= t["dec"] <= 90
        assert t["background"] and t["capabilities"]
    wise = next(t for t in BUILTIN_TARGETS if t["slug"] == "wise-0855")
    assert (wise["challenge_ra"], wise["challenge_dec"]) == (133.79513, -7.24515)
    assert "2010" in wise["challenge_note"]


@pytest.mark.parametrize("alias,slug", [
    ("barnard", "barnard"), ("Barnard's Star", "barnard"), ("barnards star", "barnard"), ("GJ 699", "barnard"),
    ("gj699", "barnard"),
    ("eps ind b", "eps-ind-b"), ("Epsilon Indi B", "eps-ind-b"), ("EPS-IND-B", "eps-ind-b"),
    ("wise 0855", "wise-0855"), ("WISE 0855-0714", "wise-0855"), ("WISE J085510.83-071442.5", "wise-0855"),
    ("wise 0855−0714", "wise-0855"),
    ("rw aur", "rw-aur"), ("RW Aurigae", "rw-aur"), ("r dra", "r-dra"), ("R Draconis", "r-dra"),
])
async def test_builtin_aliases_resolve_locally(alias, slug):
    res = await resolver.resolve(alias)
    assert res.source == "builtin"
    assert res.slug == slug
    assert res.query == alias
    assert res.classification and res.background and res.capabilities
    assert res.ref_epoch == 2000.0


async def test_resolve_decimal_coordinates_far_from_builtins():
    res = await resolver.resolve("10.5, -20.25")
    assert res.source == "coordinates"
    assert (res.ra, res.dec) == (10.5, -20.25)
    assert res.pm_ra is None and res.slug is None


async def test_resolve_challenge_coordinates_snap_to_wise_0855():
    res = await resolver.resolve("08h55m10.831s -07d14m42.53s")
    assert res.slug == "wise-0855" and res.source == "builtin"
    # canonical J2000 reference position + proper motion, so the pipeline can propagate it
    assert (res.ra, res.dec) == (133.81891, -7.24705)
    assert res.pm_ra == pytest.approx(-8123.7)


async def test_resolve_empty_raises():
    with pytest.raises(LookupError):
        await resolver.resolve("   ")


def test_match_builtin_challenge_wise_coordinates():
    hit = match_builtin(WISE_RA, WISE_DEC)
    assert hit is not None and hit["slug"] == "wise-0855"
    # tight radius still matches because the 2010.5 propagated position agrees to a few arcsec
    assert match_builtin(WISE_RA, WISE_DEC, radius_arcmin=0.2)["slug"] == "wise-0855"


def test_match_builtin_j2000_and_propagated_positions():
    for t in BUILTIN_TARGETS:
        assert match_builtin(t["ra"], t["dec"])["slug"] == t["slug"]
    # Barnard in 2026: ~2.7 arcmin from its J2000 position, found through propagation
    b = next(t for t in BUILTIN_TARGETS if t["slug"] == "barnard")
    ra26, dec26 = resolver._propagate(b, 2026.0)
    sep = resolver._sep_arcmin(ra26, dec26, b["ra"], b["dec"])
    assert sep > 2.0
    assert match_builtin(ra26, dec26, radius_arcmin=0.1)["slug"] == "barnard"


def test_match_builtin_none_for_empty_sky():
    assert match_builtin(10.0, -20.0) is None
    # just outside the radius around Eps Ind B (J2000 and propagated tracks are all far from here)
    assert match_builtin(331.04415, -56.78284 + 1.0) is None


def test_propagation_is_linear_pm():
    wise = next(t for t in BUILTIN_TARGETS if t["slug"] == "wise-0855")
    ra, dec = resolver._propagate(wise, 2026.0)
    # 26 yr * 8.12"/yr ~ 211" west, 17.5" north
    assert (wise["ra"] - ra) * math.cos(math.radians(wise["dec"])) * 3600 == pytest.approx(8.1237 * 26, rel=1e-3)
    assert (dec - wise["dec"]) * 3600 == pytest.approx(0.6732 * 26, rel=1e-3)
