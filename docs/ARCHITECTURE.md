# ASTRA — System Architecture

## 1. Overview
```
 Browser (Next.js on Vercel)                          FastAPI backend (Docker on Render)                 External
 ┌──────────────────────────────┐   JSON/PNG   ┌─────────────────────────────────────────┐
 │ Landing / Investigate / Embed│◀────────────▶│ api/  routes (REST, CORS allow-list)     │
 │  EpochPlayer (canvas)        │              │ jobs: in-process async queue (1 worker)  │
 │  SkyContext (Aladin Lite v3) │──HiPS tiles─▶│ services/ irsa_sia ─────────────────────┼──▶ IRSA SIA2 (spherex_dr1, spherex_qr3)
 │  Spectrum / LightCurve(Plotly)│  (alasky,   │           cutouts (streaming, ePSF-skip)─┼──▶ IRSA cutout service
 │  Evidence / Candidates / AI  │   CORS *)    │           crossmatch ───────────────────┼──▶ Gaia ESA TAP, SIMBAD (Harvard→CDS),
 │  demo fallback (public/demo) │              │           resolver ─────────────────────┼──▶ SkyBoT, IRSA TAP (best effort), Sesame
 └──────────────────────────────┘              │ science/  epochs, ephemeris, photometry, │
                                               │           spectrum, lightcurve, astrometry│
                                               │           difference, candidates, scoring│
                                               │           render (PNG)                   │
                                               │ ai/       gemini + grounding + templates ┼──▶ Google Gemini API
                                               │ cache/    FITS + PNG + JSON (disk)       │
                                               │ data/     SQLite (investigations, notes) │
                                               └─────────────────────────────────────────┘
```
**Principles:**
- **One backend process, no microservices.** CPU-bound science runs in a thread pool via `anyio.to_thread`. Network I/O uses async `httpx`.
- **The backend owns all external calls.** IRSA and Gaia send no CORS headers, and the Gemini key must stay server-side.
- **Deterministic science first.** AI only explains the JSON the pipeline produced.
- **Graceful degradation everywhere:**
  - A failed external service turns into evidence marked `unavailable`.
  - A failed backend turns into the precomputed demo bundle.

## 2. Backend layout (`backend/`)
```
app/
  main.py          FastAPI app, CORS (ALLOWED_ORIGINS), routers, startup (dirs, db init)
  config.py        pydantic-settings: all env vars in .env.example
  models.py        Pydantic models mirroring docs/API_CONTRACT.md
  db.py            sqlite3 (stdlib): tables investigations(id, key, status, json, created_at),
                   annotations(id, candidate_id, verdict, note, author, created_at), explain_cache
  jobs.py          asyncio.Queue + 1 worker task; progress updates written to db/memory
  pipeline.py      orchestrates stages: resolve → discover → fetch → stack → measure → crossmatch → score → render
  services/
    http.py        shared httpx.AsyncClient (timeouts, retries w/ backoff on 502/503/504, UA "ASTRA/0.1")
    irsa_sia.py    query_sia(ra, dec, collections) → list[Exposure]; VOTable parse; dedupe by did
    cutouts.py     fetch_cutout(exposure, ra, dec, size) → CutoutData (ePSF-skip streaming, disk cache)
    calib_cache.py per (detector, VERSION) full-cutout fetch → cached EPSF table + WCS-WAVE HDU
    crossmatch.py  gaia_cone, simbad_cone, catwise_cone, skybot_cone → CatalogResult
    resolver.py    parse coordinates | Sesame | SIMBAD | builtin targets
    cache.py       content-addressed disk cache helpers (sha1 keys), TTL for catalog JSON
  science/
    flags.py       bit tables, parse MSKN cards, masks
    epochs.py      visit grouping, common grid, reprojection, inverse-variance stacking
    ephemeris.py   PM + parallax predicted track
    photometry.py  aperture photometry, MJy/sr→µJy, apcorr, saturation logic
    spectrum.py    λ from WCS-W, 102-channel binning, feature table
    lightcurve.py  variability metrics
    astrometry.py  centroids + PM fit
    difference.py  Z-maps
    candidates.py  peak finding, dipole pairing, recurrence, rejection
    scoring.py     evidence items, confidence tier, classification, template summary
    render.py      PNG generation (asinh, shared limits, diverging Z, flag RGBA) via numpy + Pillow
  ai/
    gemini.py      REST client, model fallback, JSON schema output
    prompts.py     system prompt + evidence serialization
    grounding.py   number-grounding validator
    templates.py   deterministic explanation fallback
  api/
    routes_health.py routes_resolve.py routes_observations.py routes_investigations.py
    routes_frames.py routes_crossmatch.py routes_explain.py routes_annotations.py routes_report.py
scripts/
  probe_endpoints.py      live status table of every external dependency
  precompute_targets.py   runs the pipeline for the 5 targets → frontend/public/demo/
tests/                     pytest; fixtures/dr1_D6_barnard_0p02deg.fits (real DR1 cutout)
```

## 3. ePSF-skip streaming cutouts (the key performance decision)
**Problem (verified):** every cutout response carries the full EPSF table, about 3.86 MB, so a 12×12-px cutout weighs 3.9 MB. One investigation needs 100–500 exposures.

**Solution:**
1. `client.stream("GET", url)` reads the body in 2880-byte FITS blocks.
2. Parse each 2880×n header and compute the data size: `|BITPIX|/8 × ΠNAXISi` (+ PCOUNT) rounded up to 2880.
3. Keep PRIMARY, IMAGE, FLAGS, VARIANCE and ZODI. **Verified 2026-11-15 (fixture + live IRSA responses):** the HDU order is PRIMARY, IMAGE, FLAGS, VARIANCE, **ZODI**, EPSF, WCS-WAVE, so ZODI precedes EPSF and survives truncation. EPSF and WCS-WAVE are identical for all exposures of one (detector, VERSION) and come from the calib cache (step 6). `CUTOUT_MODE=full` keeps everything. When the header with `EXTNAME='EPSF'` arrives, **stop reading and close the response**. The result is about 4×(npix×4 B) + headers, roughly 20–60 KB.
4. Write the kept bytes as a valid FITS file to `cache/cutouts/{sha1(did|ra|dec|size)}.fits`.
5. **Wavelengths:** `calib_cache` downloads one full cutout per (detector, `VERSION`) and stores its `EPSF` and `WCS-WAVE` HDUs. To read λ for a truncated cutout, append the cached `WCS-WAVE` HDU in memory and build `WCS(header, fobj=hdul, key="W")`. The `CRPIX1W/2W` cards in the cutout's own IMAGE header already encode the cutout offset.
6. **Verification test (first task for Agent A):** for two different exposures of the same detector, compare λ(x, y) from the full cutout against λ from the truncated cutout plus the cached table. They must agree within 1 nm.
   - If they disagree (the lookup table is per exposure rather than per detector), fall back to fetching full cutouts with `MAX_EXPOSURES=60`, keeping only the needed HDUs on disk.
   - Record the outcome in DATA_SOURCES.md.
7. Concurrency: `asyncio.Semaphore(CUTOUT_CONCURRENCY=8)`, 3 retries with backoff, 60 s per-request timeout. Failed exposures are marked `status:"failed"` and do not abort the run.

**Cutout centre:** the PM-propagated target position at that exposure's epoch, when PM is known. Otherwise the requested position. All cutouts are then reprojected onto **one** common grid centred on the requested position (`Grid`), so motion stays visible.

**Exposure budget:** `MAX_EXPOSURES` (default 240). When exceeded, sample evenly in time within each (visit × detector) so every visit and detector stays represented. `provenance.sampling` reports which mode ran.

## 4. Caching
| What | Where | Key | TTL |
|---|---|---|---|
| SIA results | `cache/sia/` JSON | collection + rounded ra/dec | 24 h |
| Cutouts (truncated FITS) | `cache/cutouts/` | did + ra + dec + size | ∞ (immutable) |
| EPSF / WCS-WAVE | `cache/calib/` | detector + VERSION | ∞ |
| Catalog results | `cache/catalog/` JSON | service + ra/dec/r/epoch | 24 h |
| Investigation result + PNGs | `cache/inv/{id}/` + SQLite row | request key | ∞ (until redeploy) |
| AI explanations | SQLite `explain_cache` | id + subject + question hash | ∞ |

Render's free disk is ephemeral, so the cache is lost on redeploy. That is acceptable: the demo bundles cover the five targets. Annotations also live in SQLite and are lost on redeploy. For the hackathon this is documented rather than solved; the stretch fix is a Render persistent disk.

## 5. Job model
- `POST /api/investigations` computes the request key. On a cache hit it returns the existing id. Otherwise it creates a row (`queued`) and enqueues the job.
- One worker processes jobs sequentially, which protects IRSA and our CPU. Each stage updates `progress` so the UI can show a stage-by-stage checklist.
- Partial results are written after each stage so the UI can show frames before photometry finishes.
- Target runtime with a cold cache: under 90 s for 240 exposures at 3′ FOV. With a warm cache: under 5 s.

## 6. Frontend layout (`frontend/`)
```
app/
  layout.tsx            fonts, theme (dark default), header with service status chips
  page.tsx              landing: search (name/coords), 5 target cards, "how it works", honesty statement
  investigate/page.tsx  workspace; reads URL params (ra, dec, fov, name, det, mode, visit) ↔ state
  embed/page.tsx        chrome-less EpochPlayer + attribution link (iframe-able)
  about/page.tsx        science notes, limitations, data credits
components/
  SearchBar.tsx  TargetCards.tsx  StatusChips.tsx  ProgressChecklist.tsx
  EpochPlayer.tsx       canvas; modes: animate (visits or exposures), blink A/B, difference, stack; speed;
                        detector picker D1–D6 + all; overlays: predicted track, measured centroids, candidates, flags
  SkyContext.tsx        Aladin Lite (client-only); HiPS picker DSS2/2MASS/AllWISE/PanSTARRS; Gaia+SIMBAD markers;
                        FOV box; predicted track polyline
  SpectrumPlot.tsx      Plotly; per-visit series; molecular bands as shaded vrects; saturated = hollow markers
  LightCurvePlot.tsx    Plotly; per-detector series; metrics table
  MotionPanel.tsx       measured vs predicted offsets plot + PM fit table
  EvidencePanel.tsx     confidence tier badge, classification badge, novelty, item rows (verdict icon, value, threshold, why)
  CandidateList.tsx     table + thumbnails + AnnotationBox per candidate
  AiExplainer.tsx       "Explain this evidence" button; shows sections + grounding badge + disclaimer
  ProvenancePanel.tsx   collections, pipeline versions, obs_ids table with IRSA links, service statuses
  FlagLegend.tsx
lib/
  api.ts                fetch wrappers; base URL; polling; error → demo fallback
  types.ts              mirrors API_CONTRACT.md
  urlState.ts           parse/serialize URL params
  demoFallback.ts       slug lookup by proximity (< 1′) to the 5 targets; loads public/demo
  coords.ts             sexagesimal parsing/formatting
public/demo/            generated bundles
```
**Rendering:** frames are server-rendered PNGs on the shared grid. The canvas draws them with `imageSmoothingEnabled=false` (pixelated, honest) and overlays vector markers computed from `Grid` (simple TAN projection in TypeScript).
**Libraries:** next, react, tailwindcss, aladin-lite (exact version pinned), react-plotly.js, plotly.js-dist-min. Nothing else is needed.

## 7. Deployment
- **Backend:** `backend/Dockerfile`
  - Base image `python:3.13-slim`, `uv sync --frozen`, `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.
  - Render web service with env vars from `.env.example`. Set `GEMINI_API_KEY` as a secret in the dashboard.
  - Health check: `/api/health`. Use the Starter plan if free-tier memory (512 MB) proves too small for reprojection.
- **Frontend:** a Vercel project with root `frontend/` and env `NEXT_PUBLIC_API_BASE=https://<render-app>.onrender.com`.
- **CORS:** `ALLOWED_ORIGINS` lists the Vercel production URL plus `http://localhost:3000`.
- **Cold start:** the landing page pings `/api/health` on load to wake Render. When a target card is opened, the demo bundle shows immediately while the live investigation runs; the view swaps to live results when they're ready.
- **Local dev:**
  - Backend: `cd backend && uv sync && uv run uvicorn app.main:app --reload --port 8000`
  - Frontend: `cd frontend && npm i && npm run dev`

## 8. Security
- **Secrets:** the Gemini key lives only in `backend/.env` (git-ignored) and the Render secret. It is never prefixed `NEXT_PUBLIC_`, never logged, and never returned by any endpoint.
- **SSRF:** the backend fetches **only** URLs whose host is in an allow-list: `irsa.ipac.caltech.edu`, `gea.esac.esa.int`, `simbad.harvard.edu`, `simbad.cds.unistra.fr`, `cds.unistra.fr`, `vizier.idia.ac.za`, `ssp.imcce.fr`, `generativelanguage.googleapis.com`. `access_url` values from SIA are checked against this list.
- **Input validation:**
  - `ra` must be in [0, 360) and `dec` in [−90, 90].
  - `fov` must be within 1–12′ and `max_exposures` ≤ 400.
  - Name queries are limited to ≤ 100 characters.
  - Annotation notes are limited to ≤ 500 characters, stored as plain text and rendered escaped.
- **Abuse limits:** investigations are capped at 6 per minute per IP and explain calls at 10 per minute per IP, using an in-memory token bucket. Only one job runs at a time.
- **Prompt injection:** the AI receives only numeric and structured evidence. Annotation text and user questions are wrapped as data, and the system prompt says to ignore instructions inside them. Output is rendered as text, never HTML.
- **Path traversal:** frame routes validate `visit_id`, `obs_id` and `det` against the investigation record before mapping them to files.

## 9. Error handling matrix
| Failure | Behaviour |
|---|---|
| SIA 502 for one collection | retry ×3; continue with other collection; warning added |
| SIA fails for all | investigation `error` (`code:"irsa_unavailable"`); frontend offers demo bundle if near a target |
| Cutout fails | exposure `status:"failed"`; continue; warning if >20% failed |
| No exposures cover the position | `error` `code:"no_coverage"` with a friendly message |
| Target not detected | evidence `detection_snr` weakens; classification `insufficient_data`; spectrum shows upper limits |
| Catalog service down | `CatalogResult.status:"unavailable"`; evidence item verdict `unavailable`; novelty `unknown` |
| Gemini down or no key, or grounding fails twice | template explanation, `source:"template"` |
| Backend unreachable | frontend banner "Showing precomputed snapshot (generated YYYY-MM-DD)" using the demo bundle |
