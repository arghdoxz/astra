"""Internal (non-API) types shared by services/, science/ and pipeline.py.

INTERFACE SPEC — every agent implements exactly these public signatures (extra private helpers are fine).
Pipeline (Opus) calls them; CPU-bound science functions are sync and get wrapped in anyio.to_thread.

services/http.py            (A)
    def get_client() -> httpx.AsyncClient                       # shared, allow-listed, UA, timeouts
    async def fetch(method, url, *, params=None, data=None, json=None, headers=None,
                    timeout: float = 30, retries: int = 3) -> httpx.Response   # retries 502/503/504/timeouts, backoff 1/3/9 s
    def check_allowed(url: str) -> None                          # raises ValueError if host not allow-listed
    async def aclose() -> None
services/cache.py           (A)
    def cache_path(kind: str, key: str, ext: str) -> Path       # kind in {"sia","cutouts","calib","catalog","inv"}
    def read_json(kind, key, ttl_s: float | None) -> Any | None
    def write_json(kind, key, obj) -> None
    def key_of(*parts) -> str                                    # sha1 of parts; floats rounded to 4 dp
services/irsa_sia.py        (A)
    async def query_exposures(ra, dec, collections: list[str]) -> tuple[list[models.Exposure], dict[str, str]]
          # second value: {collection: "ok"|"unavailable"|"error"}; per-collection isolation
    def group_visits(exposures, gap_days: float = 30) -> list[models.Visit]    # also sets exp.visit_id, ids v0.. in time order
    def select_exposures(exposures, max_n: int, detectors: list[int]) -> tuple[list[models.Exposure], str]
          # returns (selected, "all"|"even_per_visit_detector"); even sampling in time within each (visit, detector)
services/cutouts.py         (A)
    async def fetch_cutout(exp: models.Exposure, ra: float, dec: float, size_deg: float) -> Path
    def load_cutout(path: Path, exp: models.Exposure) -> CutoutData
services/calib_cache.py     (A)
    async def ensure_calib(detector: int, version: str, sample: models.Exposure, ra: float, dec: float) -> Path | None
    def wavelength_at(cut: CutoutData, ra: float, dec: float, calib_path: Path | None) -> tuple[float, float, str]
          # (lambda_um, bandwidth_um, source) with source "wcs_wave" or "sia_band_center" (fallback = SIA em_min/em_max midpoint)
    def load_epsf(calib_path: Path | None, x_det: float, y_det: float) -> np.ndarray | None   # oversampled ePSF nearest zone
services/resolver.py        (A)
    async def resolve(q: str) -> models.ResolveResult           # raises LookupError if not found
    BUILTIN_TARGETS: list[dict]                                  # 5 targets incl. slug, classification, background, capabilities
    def parse_coordinates(q: str) -> tuple[float, float] | None

science/flags.py            (B1)
    HARD_MASK_BITS, CONTAMINATION_BITS, SATURATION_BITS = (1, 15), DEFAULT_BIT_NAMES: dict[int, str]
    def parse_mask_names(header) -> dict[int, str]
    def hard_mask(flags: np.ndarray) -> np.ndarray[bool]
    def saturation_mask(raw_flags) -> np.ndarray[bool]
    def contamination_bits(raw_flags, region_mask, names) -> list[str]
    def flag_counts(raw_flags, names) -> dict[str, int]
science/epochs.py           (B1)
    def make_grid(ra, dec, fov_arcmin, pixscale_arcsec=6.15) -> GridSpec
    def reproject_cutout(cut: CutoutData, grid: GridSpec) -> tuple[np.ndarray, np.ndarray, np.ndarray]  # (I, V, mask) on grid; mask=True bad
    def stack(images, variances, masks) -> Stack
science/render.py           (B1)
    def shared_stretch(arrays: list[np.ndarray]) -> tuple[float, float]           # asinh, 1 / 99.5 pct of the median stack
    def to_png(img, vmin, vmax, path: Path) -> None                                 # gray, NaN -> dark blue-gray, origin lower -> flip
    def zmap_png(z, path: Path, clip: float = 8.0) -> None                          # diverging
    def flags_png(hard: np.ndarray, contam: np.ndarray, path: Path) -> None         # RGBA overlay red/yellow
science/difference.py       (B1)
    def zmap(a: Stack, b: Stack, method="simple", fwhm_a_px=None, fwhm_b_px=None) -> DiffResult
science/ephemeris.py        (B2)
    def predict_track(target: models.Target, mjds: list[float]) -> list[tuple[float, float]]
    def parallax_factors(ra, dec, mjds) -> np.ndarray   # shape (n, 2): dimensionless (ΔRA·cosδ, ΔDec) offset per unit parallax
                                                        # (differential GCRS; multiply by parallax in mas -> offset in mas)
    def propagate(ra, dec, pm_ra, pm_dec, parallax, ref_epoch, mjd) -> tuple[float, float]
science/photometry.py       (B2)
    def measure(image, variance, raw_flags, hard_mask, wcs, ra, dec, fwhm_arcsec,
                flag_names: dict[int, str], epsf: np.ndarray | None = None) -> PhotResult
science/spectrum.py         (B2)
    def channel_grid() -> tuple[list[float], list[int]]          # 102 centres (17/detector, log-λ), detector per bin
    def build_spectrum(phot: list[models.PhotPoint]) -> models.Spectrum
science/lightcurve.py       (B2)
    def metrics(phot: list[models.PhotPoint], visits: list[models.Visit]) -> tuple[models.LightCurve, list[models.PhotPoint]]
          # returns curve + photometry with outlier / rel_flux filled
science/astrometry.py       (B2)
    def centroid(image, variance, wcs, ra_guess, dec_guess, fwhm_px) -> CentroidResult | None
    def fit_pm(measured: list[models.AstrometryMeasured], target: models.Target) -> models.AstrometryFit | None
    def residuals(measured, target) -> list[models.AstrometryMeasured]
    def registration_check(image, wcs, gaia_stars: list[models.CatalogMatch], fwhm_px) -> models.Registration | None

services/crossmatch.py      (D)
    async def gaia_cone(ra, dec, radius_arcsec, mjd: float | None) -> models.CatalogResult
    async def simbad_cone(ra, dec, radius_arcsec, mjd: float | None) -> models.CatalogResult
    async def catwise_cone(ra, dec, radius_arcsec, mjd: float | None) -> models.CatalogResult
    async def skybot_cone(ra, dec, radius_arcsec, mjd: float) -> models.CatalogResult
    async def crossmatch_all(ra, dec, radius_arcsec, mjd) -> models.CrossMatch
    async def gaia_field(ra, dec, radius_arcsec, mjd, gmin=10, gmax=16, limit=50) -> list[models.CatalogMatch]
    async def bright_stars(ra, dec, radius_arcmin=2.0, gmax=8.0) -> list[models.CatalogMatch] | None
science/candidates.py       (D)
    def find_candidates(diffs: list[DiffContext], grid: GridSpec, max_pm_mas_yr: float = 10000) -> list[CandidateRaw]
science/scoring.py          (D)
    def build_evidence(inp: EvidenceInput) -> models.Evidence
ai/explain.py               (D)
    async def explain(inv: models.Investigation, req: models.ExplainRequest) -> models.Explanation
db_annotations.py           (D)
    def init_annotations(conn) / insert_annotation(conn, cid, a: AnnotationIn) -> Annotation
    def list_annotations(conn, cid) -> AnnotationList
    def tallies(conn, cids: list[str]) -> dict[str, dict[str, int]]
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import numpy as np
from astropy.io.fits import Header
from astropy.wcs import WCS


@dataclass
class CutoutData:
    obs_id: str
    path: Path
    image: np.ndarray            # float32 MJy/sr, background-subtracted (median or ZODI+median), hard-masked -> NaN
    variance: np.ndarray         # MJy^2/sr^2, NaN where masked
    raw_flags: np.ndarray        # int32, unmodified FLAGS
    hard: np.ndarray             # bool, True = hard-masked
    header: Header               # IMAGE header (contains MJD-AVG, PSF_FWHM, VERSION, CRPIX*W, MSKN cards)
    wcs: WCS                     # celestial WCS (primary, 2-D)
    mjd: float
    detector: int
    version: str
    psf_fwhm_arcsec: float
    flag_names: dict[int, str]
    background_method: str       # "median" | "zodi+median"
    has_zodi: bool = False


@dataclass
class GridSpec:
    wcs: WCS
    shape: tuple[int, int]       # (ny, nx)
    ra: float
    dec: float
    pixscale_arcsec: float = 6.15

    def to_model(self):
        from .models import Grid
        ny, nx = self.shape
        return Grid(width=nx, height=ny, crval=(float(self.wcs.wcs.crval[0]), float(self.wcs.wcs.crval[1])),
                    crpix=(float(self.wcs.wcs.crpix[0]), float(self.wcs.wcs.crpix[1])),
                    cdelt_arcsec=self.pixscale_arcsec)


@dataclass
class Stack:
    S: np.ndarray                # weighted mean, MJy/sr, NaN where no data
    V: np.ndarray                # variance of S
    n: np.ndarray                # int count of contributing exposures per pixel
    mask: np.ndarray             # True where no valid data
    contam: Optional[np.ndarray] = None   # bool, any contamination bit in any contributing exposure
    fwhm_arcsec: Optional[float] = None   # median PSF_FWHM of members
    obs_ids: list[str] = field(default_factory=list)


@dataclass
class DiffResult:
    D: np.ndarray
    Z: np.ndarray
    method: str                  # "simple" | "psf_matched"
    flux_scale: float = 1.0      # applied scale on b (1.0 if not applied)
    flux_scale_measured: Optional[float] = None
    kernel_sigma_px: Optional[float] = None
    note: str = ""


@dataclass
class DiffContext:
    visit_a: str
    visit_b: str
    detector: int
    mjd_a: float
    mjd_b: float
    diff: DiffResult
    contam: np.ndarray           # bool on grid (either epoch)
    good: np.ndarray             # bool on grid (both epochs valid)


@dataclass
class PhotResult:
    flux_ujy: Optional[float]
    flux_err_ujy: Optional[float]
    snr: Optional[float]
    ab_mag: Optional[float]
    saturated: bool
    flagged_frac: float
    contamination_bits: list[str]
    apcorr: float
    apcorr_method: str           # "epsf" | "gaussian"
    x: float                     # pixel position in the image passed in (0-based)
    y: float
    rejected: bool = False       # flagged_frac > 0.3 and not saturated


@dataclass
class CentroidResult:
    ra: float
    dec: float
    x: float
    y: float
    err_arcsec: float
    snr: float
    crowded: bool
    saturated: bool = False


@dataclass
class CandidateRaw:
    id: str
    x: float
    y: float
    ra: float
    dec: float
    kind: str                    # "dipole" | "monopole"
    peak_z: float
    pm_ra: Optional[float]
    pm_dec: Optional[float]
    detectors: list[int]
    visit_pairs: list[tuple[str, str]]
    recurrence: int
    contamination_near: list[str]
    n_good_pixels: int
    rejection_reasons: list[str]


@dataclass
class EvidenceInput:
    """Everything scoring needs; None = unavailable. For candidates fill what is known."""
    subject: str                              # "target" | "candidate"
    snr: Optional[float]                      # max stack SNR at the position
    n_visits: int
    motion_sig: Optional[float] = None
    pm_measured: Optional[tuple[float, float]] = None
    catalog_pm_consistency: Optional[float] = None
    track_agreement: Optional[float] = None   # median |offset| / sigma
    variability_significant_dets: int = 0
    max_chi2_red: Optional[float] = None
    amp_sigma: Optional[float] = None
    coherent_detectors: int = 0
    recurrence: Optional[int] = None
    flagged_frac: Optional[float] = None
    saturated_frac: Optional[float] = None
    contamination: list[str] = field(default_factory=list)
    bright_neighbor_arcmin: Optional[float] = None    # nearest G<8 star; None = unknown; inf = none within search
    crossmatch: Any = None                    # models.CrossMatch
    catalog_pm_total: Optional[float] = None  # mas/yr of the matched catalog source
    catalog_variable: bool = False
    provenance: dict[str, list[str]] = field(default_factory=dict)  # item id -> obs_ids/services
    name: Optional[str] = None
