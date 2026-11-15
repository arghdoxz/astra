// Exact mirror of docs/API_CONTRACT.md (owned by Opus). Change the contract first.

export type Status = "queued" | "running" | "done" | "error";
export type ServiceStatus = "ok" | "unavailable" | "error";
export type HealthStatus = "ok" | "degraded" | "down" | "unknown" | "disabled";
export type Confidence = "insufficient" | "low" | "moderate" | "strong";
export type Stage = "resolve" | "discover" | "fetch" | "stack" | "measure" | "crossmatch" | "score" | "render" | "done";
export type Detector = number | "all";

export interface Health {
  status: string;
  version: string;
  services: Record<string, HealthStatus>;
  checked_at: string | null;
}

export interface ResolveResult extends Target {
  query: string;
  slug?: string;
  classification?: string;
  background?: string;
  capabilities?: string[];
}

export interface InvestigationRequest {
  ra: number;
  dec: number;
  fov_arcmin?: number;
  name?: string;
  max_exposures?: number;
  detectors?: number[];
  propagate_pm?: boolean;
}

export interface Investigation {
  id: string;
  status: Status;
  progress: { stage: Stage; pct: number; message: string };
  error?: { code: string; message: string } | null;
  request: { ra: number; dec: number; fov_arcmin: number; name?: string | null; detectors: number[] };
  target: Target;
  grid: Grid | null;
  provenance: Provenance;
  visits: Visit[];
  exposures: Exposure[];
  frames: Frame[];
  track: TrackPoint[];
  photometry: PhotPoint[];
  spectrum: Spectrum;
  lightcurve: LightCurve;
  astrometry: Astrometry;
  crossmatch: CrossMatch;
  evidence: Evidence;
  candidates: Candidate[];
  warnings: string[];
  methods: MethodNote[];
  created_at: string;
  generated_from: "live" | "demo_bundle" | "mock";
}

export interface MethodNote { key: string; label: string; description: string; implemented: boolean }

export interface Target {
  name?: string | null;
  ra: number;
  dec: number;
  pm_ra?: number | null;
  pm_dec?: number | null;
  parallax?: number | null;
  ref_epoch?: number | null;
  source: "sesame" | "simbad" | "gaia" | "builtin" | "coordinates";
  otype?: string | null;
}

export interface Grid {
  width: number;
  height: number;
  crval: [number, number];
  crpix: [number, number]; // 1-based FITS
  cdelt_arcsec: number;
  projection: "TAN";
  north_up: true;
}

export interface Provenance {
  collections: string[];
  pipeline_versions: string[];
  n_exposures_found: number;
  n_exposures_used: number;
  sampling: "all" | "even_per_visit_detector";
  services: Record<string, ServiceStatus>;
  generated_at: string;
  software: string;
}

export interface Visit {
  id: string;
  mjd_start: number;
  mjd_end: number;
  mjd_mean: number;
  date_label: string;
  collection: string;
  n_exposures: number;
  detectors: number[];
}

export interface Exposure {
  obs_id: string;
  detector: number;
  did: string;
  collection: string;
  visit_id: string;
  mjd: number;
  date_obs: string;
  exptime_s: number;
  em_min_um: number;
  em_max_um: number;
  wavelength_um?: number | null;
  bandwidth_um?: number | null;
  pipeline_version?: string | null;
  psf_fwhm_arcsec?: number | null;
  variance_median?: number | null;
  access_url: string;
  status: "ok" | "failed" | "skipped";
  flag_counts?: Record<string, number> | null;
}

export interface Stretch { kind: "asinh" | "linear"; vmin: number; vmax: number; unit: "MJy/sr" | "sigma" }

export interface Frame {
  kind: "visit_stack" | "exposure" | "diff" | "flags";
  visit_id?: string | null;
  visit_b?: string | null;
  obs_id?: string | null;
  method?: "simple" | "psf_matched" | null;
  detector: Detector;
  url: string; // relative to API base (or to the demo bundle folder)
  stretch?: Stretch | null;
  mjd?: number | null;
}

export interface TrackPoint { mjd: number; ra: number; dec: number; x: number; y: number; obs_id?: string | null }

export interface PhotPoint {
  obs_id: string;
  visit_id: string;
  detector: number;
  mjd: number;
  wavelength_um: number;
  bandwidth_um: number;
  flux_ujy: number | null;
  flux_err_ujy: number | null;
  ab_mag: number | null;
  snr: number | null;
  saturated: boolean;
  flagged_frac: number;
  contamination_bits: string[];
  apcorr: number;
  apcorr_method: "epsf" | "gaussian";
  x: number;
  y: number;
  outlier: boolean;
  rel_flux?: number | null;
}

export interface SpectrumPoint {
  wavelength_um: number;
  flux_ujy: number | null;
  flux_err_ujy: number | null;
  n: number;
  saturated: boolean;
  obs_ids: string[];
}

export interface Spectrum {
  channels_um: number[];
  channel_detector: number[];
  visits: { visit_id: string; points: SpectrumPoint[] }[];
  features: { species: string; wavelength_um: number; note: string }[];
  wavelength_source: "wcs_wave" | "sia_band_center";
}

export interface LightCurve {
  metrics: {
    detector: number;
    n: number;
    chi2_red: number | null;
    amp_sigma: number | null;
    frac_amp: number | null;
    significant: boolean;
  }[];
  coherent_detectors: number;
  reference_visit?: string | null;
  period_note: string;
}

export interface AstrometryMeasured {
  visit_id: string;
  mjd: number;
  ra: number;
  dec: number;
  err_arcsec: number;
  snr: number;
  detector: Detector;
  resid_ra_arcsec?: number | null;
  resid_dec_arcsec?: number | null;
  crowded: boolean;
  saturated: boolean;
}

export interface Astrometry {
  measured: AstrometryMeasured[];
  fit?: {
    pm_ra: number;
    pm_dec: number;
    pm_ra_err: number;
    pm_dec_err: number;
    chi2_red: number;
    baseline_yr: number;
    parallax_mode: "fixed_catalog" | "fitted" | "none";
    parallax?: number | null;
    parallax_err?: number | null;
    n_points: number;
  } | null;
  catalog?: { pm_ra: number; pm_dec: number; parallax: number; source: string } | null;
  consistency_sigma?: number | null;
  registration?: { n_stars: number; median_offset_arcsec: number; rms_arcsec: number; reference: "gaia_dr3" } | null;
}

export interface CatalogMatch {
  id: string;
  ra: number;
  dec: number;
  sep_arcsec: number;
  epoch_propagated: boolean;
  mag?: number | null;
  mag_band?: string | null;
  pm_ra?: number | null;
  pm_dec?: number | null;
  parallax?: number | null;
  otype?: string | null;
  variable_flag?: string | null;
  class?: string | null;
}

export interface CatalogResult {
  service: "gaia" | "simbad" | "catwise" | "skybot";
  status: ServiceStatus;
  message?: string | null;
  matches: CatalogMatch[];
}

export interface CrossMatch { gaia: CatalogResult; simbad: CatalogResult; catwise: CatalogResult; skybot: CatalogResult }

export interface EvidenceItem {
  id: string;
  label: string;
  value: number | string | null;
  unit?: string | null;
  threshold?: string | null;
  verdict: "supports" | "weakens" | "neutral" | "unavailable";
  explanation: string;
  provenance?: string[] | null;
}

export type Classification =
  | "insufficient_data"
  | "likely_artifact"
  | "solar_system_object"
  | "known_high_pm_star"
  | "known_variable"
  | "known_no_change"
  | "no_significant_change"
  | "unexplained_needs_review"
  | "low_confidence_change";

export interface Evidence {
  confidence: Confidence;
  confidence_reason: string;
  supports: number;
  weakens: number;
  classification: Classification;
  classification_label: string;
  novelty: "catalogued" | "uncatalogued" | "unknown";
  items: EvidenceItem[];
  summary: string;
}

export interface Candidate {
  id: string;
  ra: number;
  dec: number;
  x: number;
  y: number;
  kind: "dipole" | "monopole";
  peak_z: number;
  motion?: { pm_ra: number; pm_dec: number } | null;
  detectors: number[];
  visit_pairs: [string, string][];
  crossmatch: CrossMatch;
  evidence: Evidence;
  thumbnails: { visit_id: string; url: string }[];
}

export type StatementKind = "measured" | "catalog" | "interpretation" | "hypothesis" | "missing";
export type SectionKey =
  | "summary"
  | "movement"
  | "brightness"
  | "spectrum"
  | "catalog_matches"
  | "uncertainties"
  | "alternative_explanations"
  | "next_steps";

export interface Explanation {
  source: "gemini" | "template";
  model?: string | null;
  grounding: { passed: boolean; unmatched_numbers: string[] };
  sections: { key: SectionKey; title: string; statements: { kind: StatementKind; text: string }[] }[];
  disclaimer: string;
}

export interface ExplainRequest { subject: "target" | "candidate"; candidate_id?: string; question?: string }

export interface Annotation {
  id: number;
  candidate_id: string;
  verdict: "real" | "artifact" | "known" | "unsure";
  note: string;
  author?: string | null;
  created_at: string;
}

export interface AnnotationList {
  candidate_id: string;
  annotations: Annotation[];
  tally: Record<"real" | "artifact" | "known" | "unsure", number>;
}

export interface HistoryItem {
  id: string;
  status: Status;
  name?: string | null;
  ra: number;
  dec: number;
  fov_arcmin: number;
  created_at: string;
  classification?: Classification | null;
  confidence?: Confidence | null;
}

export interface ReviewItem {
  candidate_id: string;
  investigation_id: string;
  name?: string | null;
  ra: number;
  dec: number;
  kind: "dipole" | "monopole" | "target";
  classification: Classification;
  confidence: Confidence;
  tally: Record<string, number>;
  thumbnail_url?: string | null;
}

export interface ObservationsResponse {
  ra: number;
  dec: number;
  collections: { name: string; status: string; n: number }[];
  exposures: Exposure[];
  visits: Visit[];
}

export interface ApiError { error: { code: string; message: string; detail?: unknown } }
