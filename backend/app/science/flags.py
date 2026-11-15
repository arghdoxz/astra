"""SPHEREx FLAGS bit table and mask helpers (SCIENCE_REFERENCE §2.1, DATA_SOURCES §1.4).

Pure numpy; no I/O. Bit numbers are the bit *index* (value ``1 << bit``).
SOURCE (bit 21) is informational and is never masked.
"""
from __future__ import annotations

import re
from typing import Iterable, Mapping

import numpy as np

HARD_MASK_BITS: frozenset[int] = frozenset({0, 1, 2, 6, 9, 10, 11, 15, 19})
CONTAMINATION_BITS: frozenset[int] = frozenset({7, 14, 17, 20, 22, 23, 24, 25, 26, 27, 28})
SATURATION_BITS: tuple[int, ...] = (1, 15)  # OVERFLOW, NONLINEAR
INFORMATIONAL_BITS: frozenset[int] = frozenset({12, 21})  # FULLSAMPLE, SOURCE: never masked

DEFAULT_BIT_NAMES: dict[int, str] = {
    0: "TRANSIENT",
    1: "OVERFLOW",
    2: "SUR_ERROR",
    6: "NONFUNC",
    7: "DICHROIC",
    9: "MISSING_DATA",
    10: "HOT",
    11: "COLD",
    12: "FULLSAMPLE",
    14: "PHANMISS",
    15: "NONLINEAR",
    17: "PERSIST",
    19: "OUTLIER",
    20: "CROSSTALK",
    21: "SOURCE",
    22: "GHOST",
    23: "GHOST_FPA",
    24: "GHOST_EXT",
    25: "STREAK",
    26: "BLOOM",
    27: "SNOWBALL",
    28: "HALO",
}

_MSKN = re.compile(r"^MSKN(\d{4})$")


def _bits_value(bits: Iterable[int]) -> int:
    v = 0
    for b in bits:
        v |= 1 << int(b)
    return v


HARD_MASK_VALUE: int = _bits_value(HARD_MASK_BITS)
CONTAMINATION_VALUE: int = _bits_value(CONTAMINATION_BITS)
SATURATION_VALUE: int = _bits_value(SATURATION_BITS)


def parse_mask_names(header) -> dict[int, str]:
    """Bit-index -> name from ``MSKNxxxx`` cards (e.g. ``MSKN0017 = 'PERSIST'``) in a FLAGS (or IMAGE) header.

    Falls back to / is merged over DEFAULT_BIT_NAMES so unknown headers still give a full table.
    Header-provided names win. ``header`` may be None or any mapping-like astropy Header.
    """
    names = dict(DEFAULT_BIT_NAMES)
    if header is None:
        return names
    try:
        keys = list(header.keys())
    except Exception:
        return names
    for k in keys:
        m = _MSKN.match(str(k))
        if not m:
            continue
        try:
            val = str(header[k]).strip()
        except Exception:
            continue
        if val:
            names[int(m.group(1))] = val
    return names


def _as_int(flags) -> np.ndarray:
    return np.asarray(flags).astype(np.int64, copy=False)


def hard_mask(flags: np.ndarray) -> np.ndarray:
    """True where any HARD_MASK bit is set."""
    return (_as_int(flags) & HARD_MASK_VALUE) != 0


def saturation_mask(raw_flags: np.ndarray) -> np.ndarray:
    """True where OVERFLOW (bit 1) or NONLINEAR (bit 15) is set."""
    return (_as_int(raw_flags) & SATURATION_VALUE) != 0


def contamination_mask(raw_flags: np.ndarray) -> np.ndarray:
    """True where any CONTAMINATION bit is set (informational bits ignored)."""
    return (_as_int(raw_flags) & CONTAMINATION_VALUE) != 0


def contamination_bits(raw_flags: np.ndarray, region_mask: np.ndarray | None,
                       names: Mapping[int, str] | None = None) -> list[str]:
    """Names of contamination bits set in any pixel inside ``region_mask`` (None = whole array), sorted by bit."""
    names = names if names is not None else DEFAULT_BIT_NAMES
    f = _as_int(raw_flags)
    if region_mask is not None:
        region = np.asarray(region_mask, dtype=bool)
        if region.shape != f.shape:
            raise ValueError(f"region_mask shape {region.shape} != flags shape {f.shape}")
        f = f[region]
    if f.size == 0:
        return []
    present = int(np.bitwise_or.reduce(f.ravel()))
    return [names.get(b, f"BIT{b}") for b in sorted(CONTAMINATION_BITS) if present & (1 << b)]


def flag_counts(raw_flags: np.ndarray, names: Mapping[int, str] | None = None) -> dict[str, int]:
    """Flag name -> number of pixels with that bit set (only bits with count > 0), ordered by bit index.

    Covers every bit named in ``names`` (header-parsed table); unnamed set bits are reported as ``BITnn``.
    """
    names = names if names is not None else DEFAULT_BIT_NAMES
    f = _as_int(raw_flags)
    out: dict[str, int] = {}
    all_bits = set(names) | {b for b in range(31) if np.any(f & (1 << b))}
    for b in sorted(all_bits):
        c = int(np.count_nonzero(f & (1 << b)))
        if c:
            out[names.get(b, f"BIT{b}")] = c
    return out
