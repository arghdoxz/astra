# ASTRA — API Contract (v1)

This is the single source of truth shared by the backend (FastAPI) and the frontend (Next.js). `frontend/lib/types.ts` must mirror these types exactly, and `backend/app/models.py` defines them as Pydantic models.
**Change this file first, then both sides.** The base URL comes from `NEXT_PUBLIC_API_BASE`. All responses are JSON unless noted. Errors use the shape `{"error": {"code": str, "message": str, "detail"?: any}}` with a 4xx/5xx status.

Conventions: angles in **degrees** (ICRS), times in **MJD** (UTC) plus ISO strings, wavelengths in **µm**, fluxes in **µJy**, proper motions in **mas/yr**, parallax in **mas**, angular offsets in **arcsec**. Detectors are the integers `1..6`, or `"all"` for the display-only all-IR stack.

---

## Endpoints

### `GET /api/health`
```json
{ "status": "ok", "version": "0.1.0",
  "services": { "irsa_sia": HealthStatus, "gaia": HealthStatus, "simbad": HealthStatus, "skybot": HealthStatus, "gemini": HealthStatus },
  "checked_at": "2026-11-15T10:00:00Z" }
```
Service status is cached for 5 minutes. Pass `?deep=1` to force a fresh probe.

### `GET /api/resolve?q={name or coordinates}`
Accepts a name ("Barnard's Star", "eps Ind B"), sexagesimal ("08 55 10.83 -07 14 42.5", "08h55m10.831s -7d14m42.53s") or decimal degrees ("133.795 -7.245").
```json
{ "query": "eps Ind B", "name": "eps Ind B", "ra": 331.04415, "dec": -56.78284,
  "pm_ra": 3982.0, "pm_dec": -2466.8, "parallax": 270.66, "ref_epoch": 2000.0,
  "source": "sesame|simbad|gaia|builtin|coordinates", "otype": "BD*" }
```
Returns 404 with `code:"not_found"` if the name is unknown.

### `GET /api/observations?ra=&dec=&collections=spherex_dr1,spherex_qr3`
A lightweight discovery call, used by the landing-page preview and the coverage timeline.
```json
{ "ra": 0, "dec": 0, "collections": [{"name":"spherex_dr1","status":"ok","n":0}],
  "exposures": [Exposure], "visits": [Visit] }
```

### `POST /api/investigations`
Request:
```json
{ "ra": 331.04415, "dec": -56.78284, "fov_arcmin": 3, "name": "eps Ind B",
  "max_exposures": 240, "detectors": [1,2,3,4,5,6], "propagate_pm": true }
```
- `fov_arcmin` must be between 1 and 12 (default 3).
- When `propagate_pm` is true and a target with PM was resolved, the cutout centre for each exposure is the PM-propagated position.

Response `202`: `{ "id": "inv_8f3a2c", "status": "queued" }`.
Investigations are cached by `(round(ra,4), round(dec,4), fov, detectors, collections)`. A repeated request returns the existing id with `"status":"done"`.

### `GET /api/investigations?limit=20`  (investigation history)
`{ "items": [{ "id", "status", "name", "ra", "dec", "fov_arcmin", "created_at", "classification"?, "confidence"? }] }`, newest first.

### `GET /api/investigations/{id}`
Returns an `Investigation`. Poll every 1.5 s while `status` is `queued` or `running`. Partial results are allowed: fields fill in as stages finish.

### PNG frames (`image/png`, cache-control 1 day)
- `GET /api/investigations/{id}/frames/{visit_id}/{det}.png`: the visit stack (shared stretch per detector).
- `GET /api/investigations/{id}/exposures/{obs_id}/{det}.png`: a single-exposure frame for full-cadence animation.
- `GET /api/investigations/{id}/diff/{visit_a}/{visit_b}/{det}.png?method=simple|psf_matched`: Z-map, diverging colormap clipped at ±8σ. `simple` = variance-weighted subtraction of registered stacks; `psf_matched` = the sharper stack is convolved with a single Gaussian kernel σ_k = sqrt(σ_b²−σ_a²) from the header PSF_FWHM values (variance convolved with kernel²). **Neither is ZOGY / Alard–Lupton.**
- `GET /api/investigations/{id}/flags/{visit_id}/{det}.png`: RGBA overlay. Red is hard-masked; yellow is contamination.

All frames for one investigation share the same pixel grid (`Investigation.grid`). The frontend draws overlays using `grid` (pixel ↔ sky).
**Pixel convention:** every `x, y` in the API is a 0-based grid pixel in FITS/numpy orientation (`array[y, x]`, y increases **north/up**, x increases **west/right**, east is left). PNGs are written top row first, so PNG row `r` ↔ `y = height − 1 − r`; canvas overlays use `canvasY = height − 1 − y`.
**Asset URLs:** frame and thumbnail `url`s are relative. Live: `${NEXT_PUBLIC_API_BASE}${url}`. Demo bundle (`generated_from: "demo_bundle"`, id `demo_{slug}`): `/demo/{slug}/${url}` with `url` like `frames/stack_v0_6.png`.

### `GET /api/crossmatch?ra=&dec=&radius_arcsec=30&mjd=`  (radius 1–180″)
```json
{ "gaia": CatalogResult, "simbad": CatalogResult, "catwise": CatalogResult, "skybot": CatalogResult }
```

### `POST /api/investigations/{id}/explain`
Request: `{ "subject": "target" | "candidate", "candidate_id"?: "c3", "question"?: "Why is this flagged?" }`
Response (`Explanation`):
```json
{ "source": "gemini|template", "model": "gemini-flash-latest" | null,
  "grounding": { "passed": true, "unmatched_numbers": [] },
  "sections": [ { "key": "summary|movement|brightness|spectrum|catalog_matches|uncertainties|alternative_explanations|next_steps",
                  "title": "Observed movement",
                  "statements": [ { "kind": "measured|catalog|interpretation|hypothesis|missing", "text": "..." } ] } ],
  "disclaimer": "AI-generated explanation of measured evidence. Not a discovery claim." }
```
All 8 section keys are always present, in that order. Statement `kind` separates measured facts, catalog information, interpretation, hypotheses and missing evidence. Every number in `text` must appear in the evidence JSON (grounding check), otherwise the template is used.
Rate limit: 10 requests per minute per IP. Results are cached per `(id, subject, candidate_id, question)`.

### `GET /api/candidates/{candidate_id}/annotations` and `POST` the same path
POST body: `{ "verdict": "real|artifact|known|unsure", "note": "≤500 chars", "author": "≤40 chars, optional" }`
Response: `{ "candidate_id": "...", "annotations": [Annotation], "tally": {"real":0,"artifact":0,"known":0,"unsure":0} }`
`candidate_id` is globally unique: `{investigation_id}:{cid}`.

### `GET /api/candidates?limit=50`  (citizen-science review queue)
`{ "items": [{ "candidate_id": "inv_x:c0", "investigation_id", "name", "ra", "dec", "kind", "classification", "confidence", "tally": {...}, "thumbnail_url"? }] }`.
Target evidence is reviewable too, under `candidate_id = "{investigation_id}:target"`.

### `GET /api/investigations/{id}/report.json`, `/report.csv`, `/report.md`
- The JSON report is the full `Investigation` plus the annotations and an AI explanation if one was generated.
- The CSV report contains the photometry table.
- The Markdown report is a human-readable investigation summary (evidence table, measurements, provenance, annotations).

---

## Types (TypeScript notation)

```ts
type Status = "queued" | "running" | "done" | "error";
type ServiceStatus = "ok" | "unavailable" | "error";            // per-investigation catalog calls
type HealthStatus = "ok" | "degraded" | "down" | "unknown" | "disabled";   // /api/health only
type Confidence = "insufficient" | "low" | "moderate" | "strong";

interface Investigation {
  id: string;
  status: Status;
  progress: { stage: "resolve"|"discover"|"fetch"|"stack"|"measure"|"crossmatch"|"score"|"render"|"done";
              pct: number; message: string };
  error?: { code: string; message: string };
  request: { ra: number; dec: number; fov_arcmin: number; name?: string; detectors: number[] };
  target: Target;
  grid: Grid;
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
  evidence: Evidence;                 // for the requested target
  candidates: Candidate[];            // field change candidates (may be empty)
  warnings: string[];                 // human-readable, e.g. "Target saturated in 92% of exposures"
  methods: { key: string; label: string; description: string; implemented: boolean }[];  // honest method notes
  created_at: string;                 // ISO
  generated_from: "live" | "demo_bundle" | "mock";   // demo bundles are REAL precomputed data; "mock" = dev placeholder only
}

interface Target {
  name?: string; ra: number; dec: number;            // as requested/resolved
  pm_ra?: number; pm_dec?: number; parallax?: number; ref_epoch?: number;
  source: "sesame"|"simbad"|"gaia"|"builtin"|"coordinates";
  otype?: string;
}

interface Grid {                      // common reprojection grid for all frames
  width: number; height: number;      // pixels
  crval: [number, number];            // deg, ICRS, at grid centre
  crpix: [number, number];            // 1-based FITS convention
  cdelt_arcsec: number;               // 6.15
  projection: "TAN"; north_up: true;  // east left
}

interface Provenance {
  collections: string[];              // e.g. ["spherex_dr1","spherex_qr3"]
  pipeline_versions: string[];        // FITS VERSION values, e.g. ["7.0.5"]
  n_exposures_found: number; n_exposures_used: number;
  sampling: "all" | "even_per_visit_detector";
  services: Record<string, ServiceStatus>;
  generated_at: string;               // ISO
  software: string;                   // "ASTRA 0.1.0"
}

interface Visit {
  id: string;                         // "v0", "v1", … in time order
  mjd_start: number; mjd_end: number; mjd_mean: number;
  date_label: string;                 // "2025-08 (DR1)"
  collection: string;
  n_exposures: number; detectors: number[];
}

interface Exposure {
  obs_id: string; detector: number; did: string;     // obs_publisher_did
  collection: string; visit_id: string;
  mjd: number; date_obs: string; exptime_s: number;
  em_min_um: number; em_max_um: number;              // whole-detector bandpass from SIA
  wavelength_um?: number; bandwidth_um?: number;     // at the target pixel, from WCS-WAVE
  pipeline_version?: string;                         // FITS VERSION
  psf_fwhm_arcsec?: number;
  variance_median?: number;                          // MJy²/sr² within the cutout
  access_url: string;
  status: "ok" | "failed" | "skipped";
  flag_counts?: Record<string, number>;               // flag name → pixel count within the cutout
}

interface Frame {
  kind: "visit_stack" | "exposure" | "diff" | "flags";
  visit_id?: string; visit_b?: string; obs_id?: string;
  method?: "simple" | "psf_matched";                  // diff frames only
  detector: number | "all";
  url: string;                                        // relative to API base
  stretch?: { kind: "asinh" | "linear"; vmin: number; vmax: number; unit: "MJy/sr" | "sigma" };
  mjd?: number;
}

interface TrackPoint { mjd: number; ra: number; dec: number; x: number; y: number; obs_id?: string }

interface PhotPoint {
  obs_id: string; visit_id: string; detector: number; mjd: number;
  wavelength_um: number; bandwidth_um: number;
  flux_ujy: number | null; flux_err_ujy: number | null; ab_mag: number | null;
  snr: number | null;
  saturated: boolean;                                 // OVERFLOW/NONLINEAR in aperture → lower limit
  flagged_frac: number;
  contamination_bits: string[];
  apcorr: number; apcorr_method: "epsf" | "gaussian";
  x: number; y: number;                               // grid pixel position measured at
  outlier: boolean;                                   // robust |flux − median| > 5·MAD-σ within detector
  rel_flux?: number | null;                           // flux / median flux of the same λ bin in the reference visit
}

interface Spectrum {
  channels_um: number[];                              // 102 bin centres
  channel_detector: number[];                         // detector of each bin (17 per detector)
  visits: { visit_id: string; points: { wavelength_um: number; flux_ujy: number | null; flux_err_ujy: number | null;
                                         n: number; saturated: boolean; obs_ids: string[] }[] }[];  // null flux = no data (gap)
  wavelength_source: "wcs_wave" | "sia_band_center";  // how λ at the target pixel was derived
  features: { species: string; wavelength_um: number; note: string }[];
}

interface LightCurve {
  metrics: { detector: number; n: number; chi2_red: number | null; amp_sigma: number | null;
             frac_amp: number | null; significant: boolean }[];
  coherent_detectors: number;                         // detectors changing in the same sense
  reference_visit?: string;
  period_note: string;                                // always explains that no period is claimed from few epochs
}

interface Astrometry {
  measured: { visit_id: string; mjd: number; ra: number; dec: number; err_arcsec: number; snr: number; detector: number | "all";
              resid_ra_arcsec?: number; resid_dec_arcsec?: number;   // observed − predicted track (arcsec, RA·cosδ)
              crowded: boolean; saturated: boolean }[];
  fit?: { pm_ra: number; pm_dec: number; pm_ra_err: number; pm_dec_err: number; chi2_red: number;
          baseline_yr: number; parallax_mode: "fixed_catalog" | "fitted" | "none";
          parallax?: number; parallax_err?: number; n_points: number };
  registration?: { n_stars: number; median_offset_arcsec: number; rms_arcsec: number; reference: "gaia_dr3" };
  catalog?: { pm_ra: number; pm_dec: number; parallax: number; source: string };
  consistency_sigma?: number;
}

interface CatalogResult {
  service: "gaia" | "simbad" | "catwise" | "skybot";
  status: ServiceStatus; message?: string;
  matches: { id: string; ra: number; dec: number; sep_arcsec: number; epoch_propagated: boolean;
             mag?: number; mag_band?: string; pm_ra?: number; pm_dec?: number; parallax?: number;
             otype?: string; variable_flag?: string; class?: string }[];
}
interface CrossMatch { gaia: CatalogResult; simbad: CatalogResult; catwise: CatalogResult; skybot: CatalogResult }

interface EvidenceItem {
  id: string;                     // see SCIENCE_REFERENCE §5
  label: string;                  // "Motion significance"
  value: number | string | null;
  unit?: string;
  threshold?: string;             // "≥ 5σ"
  verdict: "supports" | "weakens" | "neutral" | "unavailable";
  explanation: string;            // deterministic plain-language sentence with the numbers
  provenance?: string[];          // obs_ids / services
}

interface Evidence {
  confidence: Confidence;         // transparent rule-based tier, NOT a probability (SCIENCE_REFERENCE §5)
  confidence_reason: string;      // which rule produced the tier
  supports: number; weakens: number;   // counts of items by verdict
  classification: "insufficient_data" | "likely_artifact" | "solar_system_object" | "known_high_pm_star"
                | "known_variable" | "known_no_change" | "no_significant_change"
                | "unexplained_needs_review" | "low_confidence_change";
  classification_label: string;   // human text
  novelty: "catalogued" | "uncatalogued" | "unknown";
  items: EvidenceItem[];
  summary: string;                // deterministic template summary (always present, AI-free)
}

interface Candidate {
  id: string;                     // "c0"…
  ra: number; dec: number; x: number; y: number;
  kind: "dipole" | "monopole";
  peak_z: number;
  motion?: { pm_ra: number; pm_dec: number };   // from dipole, mas/yr (rough)
  detectors: number[];
  visit_pairs: [string, string][];
  crossmatch: CrossMatch;
  evidence: Evidence;
  thumbnails: { visit_id: string; url: string }[];
}

interface Annotation { id: number; candidate_id: string; verdict: "real"|"artifact"|"known"|"unsure";
                       note: string; author?: string; created_at: string }
```

## Demo bundle format (static fallback)
`frontend/public/demo/{slug}/investigation.json` is an `Investigation`. Its frame `url`s are rewritten to relative static paths (`frames/v0_6.png`, …). Slugs: `barnard`, `eps-ind-b`, `wise-0855`, `rw-aur`, `r-dra`. `frontend/public/demo/index.json` lists `[{slug, name, ra, dec, fov_arcmin}]`. Bundles are generated by `backend/scripts/precompute_targets.py`.
