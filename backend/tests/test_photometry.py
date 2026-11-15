import math
import warnings
from pathlib import Path

import numpy as np
from astropy.io import fits
from astropy.wcs import WCS
from scipy.special import erf

from app.core_types import PhotResult
from app.science import photometry

FIXTURE = Path(__file__).parent / "fixtures" / "dr1_D6_barnard_0p02deg.fits"
PIX = 6.15
FWHM = 15.0   # arcsec (2.44 px): well sampled enough for a 3% flux test
OMEGA = (PIX / 206264.80624709636) ** 2
NAMES = {7: "PERSIST", 1: "SATURATED"}


def make_wcs(nx, ny, ra=150.0, dec=2.0):
    w = WCS(naxis=2)
    w.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    w.wcs.crval = [ra, dec]
    w.wcs.crpix = [(nx + 1) / 2, (ny + 1) / 2]
    w.wcs.cdelt = [-PIX / 3600, PIX / 3600]
    return w


def gaussian_image(n, x0, y0, flux_ujy, fwhm_arcsec=FWHM, bkg=0.5):
    """Pixel-integrated Gaussian in MJy/sr with total flux flux_ujy."""
    sigma = fwhm_arcsec / PIX / 2.3548200450309493
    edges = np.arange(n + 1) - 0.5

    def cdf(e, c):
        return 0.5 * (1 + erf((e - c) / (sigma * math.sqrt(2))))

    px = np.diff(cdf(edges, x0))
    py = np.diff(cdf(edges, y0))
    total_mjysr = flux_ujy / (1e12 * OMEGA)
    return bkg + total_mjysr * np.outer(py, px)


def setup(n=41, x0=20.3, y0=19.8, flux=1e5):
    w = make_wcs(n, n)
    img = gaussian_image(n, x0, y0, flux)
    var = np.full((n, n), 1e-4)
    raw = np.zeros((n, n), dtype=np.int32)
    hard = np.zeros((n, n), dtype=bool)
    ra, dec = w.all_pix2world(x0, y0, 0)
    return w, img, var, raw, hard, float(ra), float(dec)


def test_recovers_flux_gaussian_apcorr():
    w, img, var, raw, hard, ra, dec = setup()
    r = photometry.measure(img, var, raw, hard, w, ra, dec, FWHM, NAMES)
    assert isinstance(r, PhotResult)
    assert not r.rejected and not r.saturated
    assert r.apcorr_method == "gaussian"
    assert abs(r.flux_ujy / 1e5 - 1) < 0.03
    assert r.flux_err_ujy > 0 and r.snr > 10
    assert abs(r.ab_mag - (23.9 - 2.5 * math.log10(r.flux_ujy))) < 1e-9
    assert abs(r.x - 20.3) < 1e-6 and abs(r.y - 19.8) < 1e-6
    assert r.flagged_frac == 0.0


def test_saturation_from_raw_flags_gives_lower_limit():
    w, img, var, raw, hard, ra, dec = setup()
    raw[19:21, 20:22] |= 1 << 1           # saturated core
    hard |= (raw & (1 << 1)) != 0
    img = img.copy()
    img[hard] = np.nan
    r = photometry.measure(img, var, raw, hard, w, ra, dec, FWHM, NAMES)
    assert r.saturated is True
    assert not r.rejected
    assert r.flux_ujy is not None and r.flux_ujy < 1e5     # lower limit
    assert r.flagged_frac == 0.0                            # saturation bits excluded from flagged_frac


def test_flagged_fraction_rejects():
    w, img, var, raw, hard, ra, dec = setup()
    raw[16:25, 16:25] |= 1                # bit 0 (hard, non-saturation) over the aperture
    hard |= (raw & 1) != 0
    img = img.copy()
    img[hard] = np.nan
    r = photometry.measure(img, var, raw, hard, w, ra, dec, FWHM, NAMES)
    assert r.rejected is True and r.flux_ujy is None and r.flagged_frac > 0.3


def test_contamination_bits_named():
    w, img, var, raw, hard, ra, dec = setup()
    raw[20, 22] |= 1 << 7
    r = photometry.measure(img, var, raw, hard, w, ra, dec, FWHM, NAMES)
    assert "PERSIST" in r.contamination_bits


def test_epsf_aperture_correction_used():
    w, img, var, raw, hard, ra, dec = setup()
    n = 33
    yy, xx = np.indices((n, n))
    sig_os = FWHM / PIX / 2.3548200450309493 * 5
    epsf = np.exp(-((xx - 16) ** 2 + (yy - 16) ** 2) / (2 * sig_os ** 2))
    epsf /= epsf.sum()
    r = photometry.measure(img, var, raw, hard, w, ra, dec, FWHM, NAMES, epsf=epsf)
    assert r.apcorr_method == "epsf"
    assert 0.5 < r.apcorr < 1.0


def test_off_image_and_edge_do_not_raise():
    w, img, var, raw, hard, ra, dec = setup()
    ra2, dec2 = w.all_pix2world(-6.0, 10.0, 0)
    r = photometry.measure(img, var, raw, hard, w, float(ra2), float(dec2), FWHM, NAMES)
    assert r.rejected and r.flux_ujy is None
    ra3, dec3 = w.all_pix2world(0.5, 20.0, 0)
    r = photometry.measure(img, var, raw, hard, w, float(ra3), float(dec3), FWHM, NAMES)
    assert isinstance(r, PhotResult)
    assert r.rejected or math.isfinite(r.flux_ujy)


def test_forced_snr_on_stack():
    w, img, var, raw, hard, ra, dec = setup()
    s = photometry.forced_snr_on_stack(img, var, w, ra, dec, FWHM / PIX)
    assert s is not None and s > 10
    ra2, dec2 = w.all_pix2world(-5.0, 5.0, 0)
    assert photometry.forced_snr_on_stack(img, var, w, float(ra2), float(dec2), FWHM / PIX) is None


def test_real_fixture_clean_result():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with fits.open(FIXTURE) as h:
            hdr = h["IMAGE"].header
            img = h["IMAGE"].data.astype(float)
            var = h["VARIANCE"].data.astype(float)
            raw = h["FLAGS"].data.astype(np.int32)
            fwhm = float(hdr["PSF_FWHM"])
            epsf = np.array(h["EPSF"].data[200]["EPSF"]).reshape(33, 33)
        w = WCS(hdr)
    hard_bits = (0, 1, 2, 6, 9, 10, 11, 15, 19)
    hm = np.zeros(img.shape, dtype=bool)
    for b in hard_bits:
        hm |= ((raw >> b) & 1).astype(bool)
    img = img - np.nanmedian(img)
    img = np.where(hm, np.nan, img)
    ra, dec = w.all_pix2world(5.5, 5.5, 0)
    for e in (None, epsf):
        r = photometry.measure(img, var, raw, hm, w, float(ra), float(dec), fwhm, {}, epsf=e)
        assert isinstance(r, PhotResult)
        assert r.rejected or (r.flux_ujy is not None and math.isfinite(r.flux_ujy))
