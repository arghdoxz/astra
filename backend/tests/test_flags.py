from pathlib import Path

import numpy as np
import pytest
from astropy.io import fits

from app.science import flags as F

FIXTURE = Path(__file__).parent / "fixtures" / "dr1_D6_barnard_0p02deg.fits"


@pytest.fixture(scope="module")
def fixture_flags():
    with fits.open(FIXTURE) as h:
        return h["FLAGS"].data.astype(np.int32).copy(), h["FLAGS"].header.copy()


def test_bit_sets_match_spec():
    assert F.HARD_MASK_BITS == {0, 1, 2, 6, 9, 10, 11, 15, 19}
    assert F.CONTAMINATION_BITS == {7, 14, 17, 20, 22, 23, 24, 25, 26, 27, 28}
    assert tuple(F.SATURATION_BITS) == (1, 15)
    assert 21 not in F.HARD_MASK_BITS and 21 not in F.CONTAMINATION_BITS  # SOURCE informational
    assert not (F.HARD_MASK_BITS & F.CONTAMINATION_BITS)


def test_parse_mask_names_from_fixture_header(fixture_flags):
    _, hdr = fixture_flags
    names = F.parse_mask_names(hdr)
    assert names[0] == "TRANSIENT"
    assert names[17] == "PERSIST"
    assert names[21] == "SOURCE"
    assert names[28] == "HALO"
    for b, n in F.DEFAULT_BIT_NAMES.items():
        assert names[b] == n  # header agrees with the fallback table


def test_parse_mask_names_fallback_and_override():
    assert F.parse_mask_names(None) == F.DEFAULT_BIT_NAMES
    hdr = fits.Header()
    hdr["MSKN0017"] = "PERSIST_X"
    names = F.parse_mask_names(hdr)
    assert names[17] == "PERSIST_X"
    assert names[0] == "TRANSIENT"


def test_hard_mask_synthetic():
    f = np.zeros((3, 4), dtype=np.int32)
    f[0, 0] = 1 << 1      # OVERFLOW -> hard
    f[0, 1] = 1 << 21     # SOURCE -> never masked
    f[0, 2] = 1 << 17     # PERSIST -> contamination, not hard
    f[0, 3] = 1 << 19     # OUTLIER -> hard
    f[1, 0] = (1 << 12) | (1 << 21)  # informational only
    hm = F.hard_mask(f)
    assert hm[0, 0] and hm[0, 3]
    assert not hm[0, 1] and not hm[0, 2] and not hm[1, 0]
    assert hm.sum() == 2


def test_saturation_mask():
    f = np.zeros((2, 2), dtype=np.int32)
    f[0, 0] = 1 << 1
    f[0, 1] = 1 << 15
    f[1, 0] = 1 << 0      # TRANSIENT: hard but not saturation
    sat = F.saturation_mask(f)
    assert sat[0, 0] and sat[0, 1] and not sat[1, 0] and not sat[1, 1]


def test_contamination_bits_region():
    names = F.DEFAULT_BIT_NAMES
    f = np.zeros((4, 4), dtype=np.int32)
    f[1, 1] = 1 << 17
    f[3, 3] = (1 << 28) | (1 << 21)
    region = np.zeros((4, 4), dtype=bool)
    region[0:2, 0:2] = True
    assert F.contamination_bits(f, region, names) == ["PERSIST"]
    region[3, 3] = True
    assert F.contamination_bits(f, region, names) == ["PERSIST", "HALO"]  # SOURCE excluded
    assert F.contamination_bits(f, np.zeros((4, 4), bool), names) == []


def test_flag_counts_synthetic():
    f = np.zeros((3, 3), dtype=np.int32)
    f[0, 0] = (1 << 1) | (1 << 21)
    f[0, 1] = 1 << 21
    cnt = F.flag_counts(f, F.DEFAULT_BIT_NAMES)
    assert cnt == {"OVERFLOW": 1, "SOURCE": 2}


def test_fixture_masks_consistent(fixture_flags):
    flags, hdr = fixture_flags
    names = F.parse_mask_names(hdr)
    hm = F.hard_mask(flags)
    assert hm.shape == flags.shape and hm.dtype == bool
    expected = np.zeros(flags.shape, bool)
    for b in F.HARD_MASK_BITS:
        expected |= (flags & (1 << b)) != 0
    assert np.array_equal(hm, expected)
    counts = F.flag_counts(flags, names)
    for name, c in counts.items():
        assert 0 < c <= flags.size
    # SOURCE (if present) must not influence the hard mask
    src = (flags & (1 << 21)) != 0
    only_src = src & ((flags & F.HARD_MASK_VALUE) == 0)
    assert not np.any(hm & only_src)
    # contamination names are all contamination-bit names
    cont_names = {names[b] for b in F.CONTAMINATION_BITS}
    assert set(F.contamination_bits(flags, None, names)) <= cont_names
