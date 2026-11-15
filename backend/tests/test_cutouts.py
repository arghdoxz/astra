"""Offline tests for cutout loading and the ePSF-skip FITS block parser (real DR1 fixture, no network)."""
from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pytest
from astropy.io import fits

from app import models
from app.services import cache, cutouts

FIXTURE = Path(__file__).parent / "fixtures" / "dr1_D6_barnard_0p02deg.fits"


@pytest.fixture(scope="module")
def raw_bytes() -> bytes:
    return FIXTURE.read_bytes()


@pytest.fixture(scope="module")
def exp() -> models.Exposure:
    return models.Exposure(
        obs_id="2025W33_2C_0321_1", detector=6, did="ivo://irsa.ipac/spherex_dr1?2025W33_2C_0321_1/D6",
        collection="spherex_dr1", mjd=60902.864715, date_obs="2025-08-15T20:45:11", exptime_s=113.58,
        em_min_um=4.4115, em_max_um=5.0096,
        access_url="https://irsa.ipac.caltech.edu/ibe/data/spherex/dr1/level2/2025W33_2C/x.fits",
    )


# ------------------------------------------------------------------------------------------ load_cutout
def test_load_cutout_header_fields(exp):
    cut = cutouts.load_cutout(FIXTURE, exp)
    assert cut.detector == 6
    assert cut.version == "7.0.5"
    assert cut.mjd == pytest.approx(60902.865, abs=1e-3)  # MJD-AVG
    assert cut.obs_id == exp.obs_id
    assert cut.psf_fwhm_arcsec == pytest.approx(9.04, abs=0.01)
    assert cut.image.shape == cut.variance.shape == cut.raw_flags.shape == cut.hard.shape == (12, 12)
    assert cut.image.dtype == np.float32 and cut.raw_flags.dtype == np.int32
    assert cut.wcs.naxis == 2 and cut.wcs.has_celestial
    assert cut.has_zodi and cut.background_method == "zodi+median"
    assert cut.flag_names[21] == "SOURCE" and cut.flag_names[0] == "TRANSIENT"
    for card in ("MJD-AVG", "PSF_FWHM", "VERSION", "CRPIX1W", "CRPIX2W", "MSKN0021"):
        assert card in cut.header


def test_hard_mask_and_nan_propagation(exp):
    with fits.open(FIXTURE) as h:
        flags = np.array(h["FLAGS"].data, dtype=np.int64)
        orig_variance = np.array(h["VARIANCE"].data)
    hard_bits = (0, 1, 2, 6, 9, 10, 11, 15, 19)
    expect = np.zeros(flags.shape, bool)
    for b in hard_bits:
        expect |= (flags & (1 << b)) != 0

    cut = cutouts.load_cutout(FIXTURE, exp)
    assert expect.any(), "fixture should contain at least one hard-masked pixel"
    assert np.array_equal(cut.hard, expect | cut.hard)  # hard is at least the flag mask
    assert np.all(np.isnan(cut.image[cut.hard]))
    assert np.all(np.isnan(cut.variance[cut.hard]))
    assert np.all(np.isfinite(cut.image[~cut.hard]))
    assert np.all(np.isfinite(cut.variance[~cut.hard]))
    # unmasked variance is untouched
    assert np.array_equal(cut.variance[~cut.hard], orig_variance[~cut.hard])


def test_raw_flags_preserved_and_source_never_masked(exp):
    with fits.open(FIXTURE) as h:
        flags = np.array(h["FLAGS"].data, dtype=np.int32)
    cut = cutouts.load_cutout(FIXTURE, exp)
    assert np.array_equal(cut.raw_flags, flags)
    source_only = (flags & (1 << 21) != 0) & ((flags & sum(1 << b for b in (0, 1, 2, 6, 9, 10, 11, 15, 19))) == 0)
    assert source_only.sum() > 0
    assert not cut.hard[source_only].any()
    assert np.all(np.isfinite(cut.image[source_only]))


def test_background_subtracted(exp):
    cut = cutouts.load_cutout(FIXTURE, exp)
    assert abs(float(np.nanmedian(cut.image))) < 0.2 * float(np.nanstd(cut.image) + 1e-9) + 1e-3


# ------------------------------------------------------------------------------------------ block parser
async def _chunks(data: bytes, size: int, consumed: list[int] | None = None):
    for i in range(0, len(data), size):
        if consumed is not None:
            consumed.append(i)
        yield data[i:i + size]


def _hdu_names_before_epsf(raw: bytes) -> list[str]:
    names: list[str] = []
    with fits.open(io.BytesIO(raw)) as h:
        for hdu in h:
            if hdu.name == "EPSF":
                break
            names.append(hdu.name)
    return names


@pytest.mark.parametrize("chunk", [65536, 4096, 1000, 2880, 7])
async def test_truncate_stream_keeps_pre_epsf_hdus(raw_bytes, chunk):
    expected = _hdu_names_before_epsf(raw_bytes)
    assert {"IMAGE", "FLAGS", "VARIANCE"} <= set(expected)
    if chunk == 7:  # tiny chunks on the 3.9 MB fixture would be slow: only parse the head
        raw = raw_bytes[: 200_000]
    else:
        raw = raw_bytes
    out, kept = await cutouts.truncate_stream(_chunks(raw, chunk))
    assert kept == ["PRIMARY"] + [n for n in expected if n != "PRIMARY"]
    assert "EPSF" not in kept and "WCS-WAVE" not in kept
    with fits.open(io.BytesIO(out)) as h:
        assert [x.name for x in h] == kept
        with fits.open(FIXTURE) as orig:
            for name in ("IMAGE", "FLAGS", "VARIANCE"):
                assert np.array_equal(h[name].data, orig[name].data, equal_nan=True)
                assert h[name].header["EXTNAME"] == name
    assert len(out) % 2880 == 0 and len(out) < 100_000  # ePSF table (3.9 MB) is gone


async def test_truncate_stream_stops_reading_at_epsf(raw_bytes):
    consumed: list[int] = []
    await cutouts.truncate_stream(_chunks(raw_bytes, 2880, consumed))
    total_chunks = (len(raw_bytes) + 2879) // 2880
    assert len(consumed) < total_chunks // 10  # stopped right after the EPSF header, not at EOF


async def test_truncated_file_is_loadable(raw_bytes, exp, tmp_path):
    out, _ = await cutouts.truncate_stream(_chunks(raw_bytes, 8192))
    p = tmp_path / "trunc.fits"
    p.write_bytes(out)
    full = cutouts.load_cutout(FIXTURE, exp)
    trunc = cutouts.load_cutout(p, exp)
    assert trunc.version == full.version and trunc.detector == 6
    assert np.array_equal(trunc.image, full.image, equal_nan=True)
    assert np.array_equal(trunc.raw_flags, full.raw_flags)


async def test_truncate_stream_rejects_non_fits():
    with pytest.raises(ValueError):
        await cutouts.truncate_stream(_chunks(b"<html>502 Proxy Error</html>" * 200, 1000))


async def test_truncate_stream_detects_truncation_inside_image(raw_bytes):
    with pytest.raises(ValueError):
        await cutouts.truncate_stream(_chunks(raw_bytes[: 2880 * 2 + 2880 * 10], 4096))  # cut inside FLAGS/IMAGE data


# ------------------------------------------------------------------------------------------ cache keys
def test_key_of_rounds_floats_to_4dp():
    assert cache.key_of("did", 269.45201, 4.69341) == cache.key_of("did", 269.45204, 4.69344)
    assert cache.key_of("did", 269.4520, 4.6933) != cache.key_of("did", 269.4521, 4.6933)
    assert cache.key_of("a", np.float64(1.00001)) == cache.key_of("a", 1.0)
