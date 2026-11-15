"""Pydantic mirror of docs/API_CONTRACT.md. Change the contract doc first, then this file and frontend/lib/types.ts."""
from __future__ import annotations

from typing import Any, Literal, Optional, Union

from pydantic import BaseModel, Field

Status = Literal["queued", "running", "done", "error"]
ServiceStatus = Literal["ok", "unavailable", "error"]
HealthStatus = Literal["ok", "degraded", "down", "unknown", "disabled"]
Confidence = Literal["insufficient", "low", "moderate", "strong"]
Stage = Literal["resolve", "discover", "fetch", "stack", "measure", "crossmatch", "score", "render", "done"]
Classification = Literal[
    "insufficient_data", "likely_artifact", "solar_system_object", "known_high_pm_star",
    "known_variable", "known_no_change", "no_significant_change",
    "unexplained_needs_review", "low_confidence_change",
]
Verdict = Literal["supports", "weakens", "neutral", "unavailable"]
Detector = Union[int, Literal["all"]]


# ---------- requests ----------
class InvestigationRequest(BaseModel):
    ra: float = Field(ge=0, lt=360)
    dec: float = Field(ge=-90, le=90)
    fov_arcmin: float = Field(default=3, ge=1, le=12)
    name: Optional[str] = Field(default=None, max_length=100)
    max_exposures: int = Field(default=240, ge=6, le=400)
    detectors: list[int] = Field(default_factory=lambda: [1, 2, 3, 4, 5, 6])
    propagate_pm: bool = True


class ExplainRequest(BaseModel):
    subject: Literal["target", "candidate"] = "target"
    candidate_id: Optional[str] = Field(default=None, max_length=40)
    question: Optional[str] = Field(default=None, max_length=300)


class AnnotationIn(BaseModel):
    verdict: Literal["real", "artifact", "known", "unsure"]
    note: str = Field(default="", max_length=500)
    author: Optional[str] = Field(default=None, max_length=40)


# ---------- core types ----------
class Progress(BaseModel):
    stage: Stage = "resolve"
    pct: float = 0
    message: str = ""


class ErrorInfo(BaseModel):
    code: str
    message: str


class RequestEcho(BaseModel):
    ra: float
    dec: float
    fov_arcmin: float
    name: Optional[str] = None
    detectors: list[int]


class Target(BaseModel):
    name: Optional[str] = None
    ra: float
    dec: float
    pm_ra: Optional[float] = None
    pm_dec: Optional[float] = None
    parallax: Optional[float] = None
    ref_epoch: Optional[float] = None
    source: Literal["sesame", "simbad", "gaia", "builtin", "coordinates"] = "coordinates"
    otype: Optional[str] = None


class ResolveResult(Target):
    query: str
    # extras for built-in targets (target library)
    slug: Optional[str] = None
    classification: Optional[str] = None
    background: Optional[str] = None
    capabilities: Optional[list[str]] = None


class Grid(BaseModel):
    width: int
    height: int
    crval: tuple[float, float]
    crpix: tuple[float, float]
    cdelt_arcsec: float = 6.15
    projection: Literal["TAN"] = "TAN"
    north_up: Literal[True] = True


class Provenance(BaseModel):
    collections: list[str] = Field(default_factory=list)
    pipeline_versions: list[str] = Field(default_factory=list)
    n_exposures_found: int = 0
    n_exposures_used: int = 0
    sampling: Literal["all", "even_per_visit_detector"] = "all"
    services: dict[str, ServiceStatus] = Field(default_factory=dict)
    generated_at: str = ""
    software: str = ""


class Visit(BaseModel):
    id: str
    mjd_start: float
    mjd_end: float
    mjd_mean: float
    date_label: str
    collection: str
    n_exposures: int
    detectors: list[int]


class Exposure(BaseModel):
    obs_id: str
    detector: int
    did: str
    collection: str
    visit_id: str = ""
    mjd: float
    date_obs: str
    exptime_s: float = 0.0
    em_min_um: float
    em_max_um: float
    wavelength_um: Optional[float] = None
    bandwidth_um: Optional[float] = None
    pipeline_version: Optional[str] = None
    psf_fwhm_arcsec: Optional[float] = None
    variance_median: Optional[float] = None
    access_url: str
    status: Literal["ok", "failed", "skipped"] = "ok"
    flag_counts: Optional[dict[str, int]] = None


class Stretch(BaseModel):
    kind: Literal["asinh", "linear"] = "asinh"
    vmin: float
    vmax: float
    unit: Literal["MJy/sr", "sigma"] = "MJy/sr"


class Frame(BaseModel):
    kind: Literal["visit_stack", "exposure", "diff", "flags"]
    visit_id: Optional[str] = None
    visit_b: Optional[str] = None
    obs_id: Optional[str] = None
    method: Optional[Literal["simple", "psf_matched"]] = None
    detector: Detector
    url: str
    stretch: Optional[Stretch] = None
    mjd: Optional[float] = None


class TrackPoint(BaseModel):
    mjd: float
    ra: float
    dec: float
    x: float
    y: float
    obs_id: Optional[str] = None


class PhotPoint(BaseModel):
    obs_id: str
    visit_id: str
    detector: int
    mjd: float
    wavelength_um: float
    bandwidth_um: float
    flux_ujy: Optional[float] = None
    flux_err_ujy: Optional[float] = None
    ab_mag: Optional[float] = None
    snr: Optional[float] = None
    saturated: bool = False
    flagged_frac: float = 0.0
    contamination_bits: list[str] = Field(default_factory=list)
    apcorr: float = 1.0
    apcorr_method: Literal["epsf", "gaussian"] = "gaussian"
    x: float
    y: float
    outlier: bool = False
    rel_flux: Optional[float] = None


class SpectrumPointOut(BaseModel):
    wavelength_um: float
    flux_ujy: Optional[float] = None
    flux_err_ujy: Optional[float] = None
    n: int = 0
    saturated: bool = False
    obs_ids: list[str] = Field(default_factory=list)


class SpectrumVisit(BaseModel):
    visit_id: str
    points: list[SpectrumPointOut]


class SpectralFeature(BaseModel):
    species: str
    wavelength_um: float
    note: str


class Spectrum(BaseModel):
    channels_um: list[float] = Field(default_factory=list)
    channel_detector: list[int] = Field(default_factory=list)
    visits: list[SpectrumVisit] = Field(default_factory=list)
    features: list[SpectralFeature] = Field(default_factory=list)
    wavelength_source: Literal["wcs_wave", "sia_band_center"] = "wcs_wave"


class LightCurveMetric(BaseModel):
    detector: int
    n: int
    chi2_red: Optional[float] = None
    amp_sigma: Optional[float] = None
    frac_amp: Optional[float] = None
    significant: bool = False


class LightCurve(BaseModel):
    metrics: list[LightCurveMetric] = Field(default_factory=list)
    coherent_detectors: int = 0
    reference_visit: Optional[str] = None
    period_note: str = (
        "No period is fitted or claimed: a few survey visits cannot constrain a period."
    )


class AstrometryMeasured(BaseModel):
    visit_id: str
    mjd: float
    ra: float
    dec: float
    err_arcsec: float
    snr: float
    detector: Detector
    resid_ra_arcsec: Optional[float] = None
    resid_dec_arcsec: Optional[float] = None
    crowded: bool = False
    saturated: bool = False


class AstrometryFit(BaseModel):
    pm_ra: float
    pm_dec: float
    pm_ra_err: float
    pm_dec_err: float
    chi2_red: float
    baseline_yr: float
    parallax_mode: Literal["fixed_catalog", "fitted", "none"]
    parallax: Optional[float] = None
    parallax_err: Optional[float] = None
    n_points: int


class AstrometryCatalog(BaseModel):
    pm_ra: float
    pm_dec: float
    parallax: float
    source: str


class Registration(BaseModel):
    n_stars: int
    median_offset_arcsec: float
    rms_arcsec: float
    reference: Literal["gaia_dr3"] = "gaia_dr3"


class Astrometry(BaseModel):
    measured: list[AstrometryMeasured] = Field(default_factory=list)
    fit: Optional[AstrometryFit] = None
    catalog: Optional[AstrometryCatalog] = None
    consistency_sigma: Optional[float] = None
    registration: Optional[Registration] = None


class CatalogMatch(BaseModel):
    id: str
    ra: float
    dec: float
    sep_arcsec: float
    epoch_propagated: bool = False
    mag: Optional[float] = None
    mag_band: Optional[str] = None
    pm_ra: Optional[float] = None
    pm_dec: Optional[float] = None
    parallax: Optional[float] = None
    otype: Optional[str] = None
    variable_flag: Optional[str] = None
    # "class" is a Python keyword; serialized as "class"
    class_: Optional[str] = Field(default=None, alias="class", serialization_alias="class")

    model_config = {"populate_by_name": True}


class CatalogResult(BaseModel):
    service: Literal["gaia", "simbad", "catwise", "skybot"]
    status: ServiceStatus = "unavailable"
    message: Optional[str] = None
    matches: list[CatalogMatch] = Field(default_factory=list)


def _unavailable(svc: str) -> CatalogResult:
    return CatalogResult(service=svc, status="unavailable", message="not queried")  # type: ignore[arg-type]


class CrossMatch(BaseModel):
    gaia: CatalogResult = Field(default_factory=lambda: _unavailable("gaia"))
    simbad: CatalogResult = Field(default_factory=lambda: _unavailable("simbad"))
    catwise: CatalogResult = Field(default_factory=lambda: _unavailable("catwise"))
    skybot: CatalogResult = Field(default_factory=lambda: _unavailable("skybot"))


class EvidenceItem(BaseModel):
    id: str
    label: str
    value: Union[float, str, None] = None
    unit: Optional[str] = None
    threshold: Optional[str] = None
    verdict: Verdict = "unavailable"
    explanation: str = ""
    provenance: Optional[list[str]] = None


class Evidence(BaseModel):
    confidence: Confidence = "insufficient"
    confidence_reason: str = ""
    supports: int = 0
    weakens: int = 0
    classification: Classification = "insufficient_data"
    classification_label: str = "Insufficient data"
    novelty: Literal["catalogued", "uncatalogued", "unknown"] = "unknown"
    items: list[EvidenceItem] = Field(default_factory=list)
    summary: str = ""


class CandidateMotion(BaseModel):
    pm_ra: float
    pm_dec: float


class Thumbnail(BaseModel):
    visit_id: str
    url: str


class Candidate(BaseModel):
    id: str
    ra: float
    dec: float
    x: float
    y: float
    kind: Literal["dipole", "monopole"]
    peak_z: float
    motion: Optional[CandidateMotion] = None
    detectors: list[int]
    visit_pairs: list[tuple[str, str]]
    crossmatch: CrossMatch = Field(default_factory=CrossMatch)
    evidence: Evidence = Field(default_factory=Evidence)
    thumbnails: list[Thumbnail] = Field(default_factory=list)


class MethodNote(BaseModel):
    key: str
    label: str
    description: str
    implemented: bool


class Investigation(BaseModel):
    id: str
    status: Status = "queued"
    progress: Progress = Field(default_factory=Progress)
    error: Optional[ErrorInfo] = None
    request: RequestEcho
    target: Target
    grid: Optional[Grid] = None
    provenance: Provenance = Field(default_factory=Provenance)
    visits: list[Visit] = Field(default_factory=list)
    exposures: list[Exposure] = Field(default_factory=list)
    frames: list[Frame] = Field(default_factory=list)
    track: list[TrackPoint] = Field(default_factory=list)
    photometry: list[PhotPoint] = Field(default_factory=list)
    spectrum: Spectrum = Field(default_factory=Spectrum)
    lightcurve: LightCurve = Field(default_factory=LightCurve)
    astrometry: Astrometry = Field(default_factory=Astrometry)
    crossmatch: CrossMatch = Field(default_factory=CrossMatch)
    evidence: Evidence = Field(default_factory=Evidence)
    candidates: list[Candidate] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    methods: list[MethodNote] = Field(default_factory=list)
    created_at: str = ""
    generated_from: Literal["live", "demo_bundle", "mock"] = "live"


# ---------- explanation ----------
SectionKey = Literal[
    "summary", "movement", "brightness", "spectrum", "catalog_matches",
    "uncertainties", "alternative_explanations", "next_steps",
]
SECTION_ORDER: list[str] = [
    "summary", "movement", "brightness", "spectrum", "catalog_matches",
    "uncertainties", "alternative_explanations", "next_steps",
]
SECTION_TITLES: dict[str, str] = {
    "summary": "Summary",
    "movement": "Observed movement",
    "brightness": "Brightness changes",
    "spectrum": "Spectral information",
    "catalog_matches": "Catalog associations",
    "uncertainties": "Uncertainties",
    "alternative_explanations": "Alternative explanations",
    "next_steps": "What to investigate next",
}


class Statement(BaseModel):
    kind: Literal["measured", "catalog", "interpretation", "hypothesis", "missing"]
    text: str


class ExplanationSection(BaseModel):
    key: SectionKey
    title: str
    statements: list[Statement]


class Grounding(BaseModel):
    passed: bool
    unmatched_numbers: list[str] = Field(default_factory=list)


DISCLAIMER = "AI-generated explanation of measured evidence. Not a discovery claim."


class Explanation(BaseModel):
    source: Literal["gemini", "template"]
    model: Optional[str] = None
    grounding: Grounding
    sections: list[ExplanationSection]
    disclaimer: str = DISCLAIMER


# ---------- annotations / lists ----------
class Annotation(BaseModel):
    id: int
    candidate_id: str
    verdict: Literal["real", "artifact", "known", "unsure"]
    note: str
    author: Optional[str] = None
    created_at: str


class AnnotationList(BaseModel):
    candidate_id: str
    annotations: list[Annotation]
    tally: dict[str, int]


class ObservationsResponse(BaseModel):
    ra: float
    dec: float
    collections: list[dict[str, Any]]
    exposures: list[Exposure]
    visits: list[Visit]
