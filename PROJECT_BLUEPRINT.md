# ASTRA — Project Blueprint

**ASTRA** is an evidence-based investigation platform for NASA SPHEREx time-domain data. It is our entry for NASA Space Apps 2026, challenge *"Planet X and SPHEREx"*.

This is the **entry point** for any engineer or AI session building ASTRA. It is self-contained; read it top to bottom, then the docs it links. Architecture decisions here are **final** unless a verified fact contradicts them.

| Doc | Purpose |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Components, data flow, ePSF-skip streaming, caching, jobs, deploy, security, error matrix |
| [docs/API_CONTRACT.md](docs/API_CONTRACT.md) | **The shared backend↔frontend contract.** Change this first. |
| [docs/SCIENCE_REFERENCE.md](docs/SCIENCE_REFERENCE.md) | Every formula, threshold, flag rule, target expectation, and the scoring and classification rules |
| [docs/DATA_SOURCES.md](docs/DATA_SOURCES.md) | Verified endpoints, exact queries, CORS, failover, package versions |
| [docs/ROADMAP.md](docs/ROADMAP.md) | Essential / High / Stretch features with owners and effort |
| [docs/SUBMISSION.md](docs/SUBMISSION.md) | Checklist, pitch, demo script |

---

## 1. The challenge and how we win
The challenge asks for a public web tool: enter RA/Dec, see SPHEREx images of that region over time as an animation, and spot movers and variables. The five test targets are Barnard's Star, Eps Ind B, WISE 0855−0714, RW Aur and R Dra.

The challenge page's judging hints (verified):
- Easy to update for new releases.
- Creative use of the 102 bands. **On-the-fly spectra earn extra credit.**
- Add or subtract epochs.
- User-chosen field of view.
- Gaia/WISE overlays.
- **Coordinates as URL params** (embeddable).
- Show contamination flags and metadata.
- Astropy and Aladin are suggested.

What the competition shipped (inspected 2026-11-14):

| Entry | Strength | Gap we exploit |
|---|---|---|
| Blackhole 102 (FearmessOp) | Rigorous Gaia-aligned astrometry pipeline | Static site with **5 fixed targets only**: no coordinate input, spectra, subtraction or overlays |
| SPHEREx Blink (Andrei25Ciuta) | Very broad feature list | **Public site runs on synthetic demo data.** Uncalibrated photometry, zero points "from memory" |

**ASTRA's differentiators:**
1. **Live real data** for any coordinate, with a demo fallback that's clearly labelled as one.
2. **Physics-predicted track** (proper motion and parallax per exposure). It catches the challenge's stale WISE 0855 coordinates, which are 21 px off by 2026.
3. **Calibrated measurements:** µJy photometry, an on-the-fly 0.75–5 µm spectrum, and a PM fit.
4. **Explainable evidence scoring.** Each item shows its number, threshold and reason, then feeds a deterministic classification. Novelty is tracked separately, and the system never claims discoveries.
5. **Cross-survey identity** across Gaia, SIMBAD, CatWISE and SkyBoT, plus SPHEREx's own 22 contamination flags as false-positive evidence.
6. **Grounded AI.** Gemini explains the evidence JSON, and a validator rejects any number not in the evidence.
7. **Human verification** (annotations) and full **provenance** (obs_ids, releases, pipeline versions).

## 2. Final decisions
| Area | Decision | Rationale |
|---|---|---|
| Frontend | Next.js (App Router) + TypeScript + Tailwind on **Vercel** | Team familiarity, fast deploy |
| Sky context | **Aladin Lite v3** via npm `aladin-lite`, exact version pinned, client-only | The CDS CDN URL returned 404 from our network |
| Plots | react-plotly.js + plotly.js-dist-min | Spectra and light curves with error bars |
| SPHEREx frames | Server-rendered PNGs on a shared grid, animated in our own canvas | Honest shared stretch, simple, fast |
| Backend | **FastAPI on Python 3.13**, managed with `uv`, Docker on **Render** | astropy ecosystem; the default local venv is Python 3.9, so always use `uv --python 3.13` |
| Science | astropy 8.0.2, photutils 3.1.1, reproject, numpy, scipy, pyvo 1.10.0 (optional) | Standard and verified on PyPI |
| HTTP | async `httpx`, direct REST/TAP calls, our own retries and timeouts | IRSA and CDS were flaky during testing, so we need control |
| Storage | Disk cache + **stdlib sqlite3** | No infrastructure to run |
| Jobs | In-process asyncio queue, 1 worker | Protects IRSA and the CPU; enough for a demo |
| AI | **Google Gemini** REST, `GEMINI_MODEL=gemini-flash-latest`, fallback `gemini-2.5-flash` | The team has a free key; both models verified available |
| Data | **SPHEREx DR1 + QR3 only**, via SIA2 + cutouts. Never QR2. Never the All-Sky Cube for time-domain work. | IRSA guidance |

**Secret handling:** `GEMINI_API_KEY` exists only in `backend/.env` (git-ignored, already created locally) and in Render secrets. Never write it anywhere else. Rotate it after the hackathon, because it was shared in chat.

**Agent rule:** orchestrating sessions must **never spawn Opus subagents**. Every agent call sets `model: "haiku"` (research and inspection) or `model: "sonnet"` (implementation) explicitly.

## 3. Verified facts the design depends on
All are detailed in DATA_SOURCES.md, live-checked 2026-11-14/15.
- **SIA2:** `https://irsa.ipac.caltech.edu/SIA?COLLECTION=spherex_dr1&POS=circle+RA+DEC+0.001` returns a VOTable with `access_url`, `t_min`/`t_max` (MJD), `energy_bandpassname` (`SPHEREx-D1..6`), `em_min`/`em_max`, `obs_publisher_did`, `s_region`. It sends **no CORS** headers and returns **intermittent 502s**.
- **Cutouts:** `{access_url}?center=RA,DEC&size=DEG` returns an MEF with IMAGE (MJy/sr), FLAGS, VARIANCE, ZODI, EPSF (~3.9 MB, always included), and WCS-WAVE. The header has `MJD-AVG`, `PSF_FWHM`, `VERSION`, and the alternate WCS `W` = WAVE-TAB.
- **Flag bits** are named in the `MSKNxxxx` cards. SOURCE (21) is informational, so never mask it. The hard mask is {0,1,2,6,9,10,11,15,19}; the contamination set is {7,14,17,20,22–28}.
- **IRSA TAP** timed out, so it stays off the critical path.
- **Other services:**
  - Gaia ESA TAP works (no CORS).
  - SIMBAD CDS was **down**; the Harvard mirror works.
  - SkyBoT works.
  - Gemini models are listed for our key.
- **A real DR1 cutout fixture** is saved at `backend/tests/fixtures/dr1_D6_barnard_0p02deg.fits`.

## 4. Development sequence
Times are hours from the start of implementation. Agent letters match the work packages in §5. Each phase ends with a **gate**: don't advance until it passes.

**Phase 0 (0:00–0:45), Opus: scaffold.**
- `backend/`: run `uv init --python 3.13`, then add `fastapi uvicorn[standard] httpx astropy==8.0.2 photutils==3.1.1 reproject numpy scipy pillow pydantic-settings python-dotenv pytest pytest-asyncio`.
  - Create `app/main.py` with `/api/health`, `config.py`, `models.py` (from API_CONTRACT), and stubbed routers.
- `frontend/`: run `npx create-next-app@latest frontend --ts --tailwind --app --eslint --no-src-dir --import-alias "@/*"` (pin the resolved version in package.json).
  - Add `lib/types.ts` from API_CONTRACT and a **mock** `public/demo/eps-ind-b/investigation.json` with plausible-shaped data marked `"mock": true`, so C can build the UI before the backend is ready.
- **Gate:** `uv run uvicorn app.main:app` serves `/api/health`, and `npm run dev` renders the landing page.

**Phase 1 (0:45–5:00), parallel: A, B, C, D.**
- **A** builds the data layer. It must deliver the **ePSF-skip λ-equivalence test first**, within 1 hour, and report the result to Opus.
- **B** builds the science modules against the fixture FITS and synthetic arrays. It owns no network code.
- **C** builds the UI against the mock JSON.
- **D** builds cross-match, scoring, classification and the template summary against synthetic evidence inputs.
- **Gate:** `pytest` passes, the A and B functions are importable, and the UI renders the mock bundle end to end.

**Phase 2 (5:00–8:00), Opus: integration.**
- Write `pipeline.py` and `jobs.py`, and wire routes per API_CONTRACT.
- Run a live investigation on **Eps Ind B** (clean, unsaturated, moving), then WISE 0855, Barnard, R Dra and RW Aur.
- Fix contract drift.
- **Gate:** all 5 targets complete live in under 3 minutes each with a cold cache, and the UI shows frames, track, spectrum, light curve and evidence.

**Phase 3 (8:00–12:00), parallel.**
- D: candidates + Gemini + annotations.
- C: Aladin overlays, Motion, Candidates, AI, Provenance panels, embed.
- B: difference maps, astrometric fit.
- E: Docker, Render, Vercel, `precompute_targets.py`.
- **Gate:** deployed URLs work, and the demo fallback works with the backend stopped.

**Phase 4 (12:00–16:00): polish and proof.**
- Science sanity checks (§7).
- Copy and accessibility pass; About/limitations page.
- README screenshots, SUBMISSION.md pitch, demo video.

**Phase 5: buffer** (at least 4 h before the deadline). Bug fixes only; no new features.

**Cut order if behind:** S → H9 CatWISE → H3 field candidates (keep target evidence) → H7 annotations → H6 Aladin overlays (keep the basic Aladin view). **Never cut:** E1–E13, the evidence panel, demo fallback, honesty language.

## 5. Agent work packages
Every agent is spawned with `model: "sonnet"` and told to read this file, API_CONTRACT.md, and the docs listed in its brief. Directory ownership is **disjoint**; only Opus edits `app/main.py`, `app/pipeline.py`, `app/jobs.py`, `app/models.py` and `docs/API_CONTRACT.md`.

### A: Data layer (`backend/app/services/{http,irsa_sia,cutouts,calib_cache,cache,resolver}.py`, `backend/scripts/probe_endpoints.py`)
Read: DATA_SOURCES §1, §2.3; ARCHITECTURE §3–4, §8 (SSRF allow-list).
1. `http.py`: a shared AsyncClient with an allow-list, timeouts, retries (502/503/504/timeouts; backoff 1/3/9 s) and UA `ASTRA/0.1 (NASA Space Apps)`.
2. `irsa_sia.py`: `async query_exposures(ra, dec, collections) -> list[Exposure]`.
   - Parse with `astropy.io.votable`. Detector = int from `energy_bandpassname`. Convert m to µm. MJD = `t_min`.
   - Dedupe by `obs_publisher_did`. Cache JSON for 24 h.
   - `group_visits(exposures, gap_days=30) -> list[Visit]`.
3. `cutouts.py`: `async fetch_cutout(exp, ra, dec, size_deg) -> Path`.
   - Streaming FITS block parser. Keep the HDUs before `EPSF`, then close the stream. Write a valid FITS file; cache it.
   - Plus `load_cutout(path) -> CutoutData` (image−zodi, variance, flags, header, celestial WCS).
4. `calib_cache.py`: `async ensure_calib(detector, version, sample_exposure) -> Path` (full cutout → EPSF + WCS-WAVE HDUs), and `wavelength_at(cutout_path, x, y) -> (λ_um, bw_um)` using the cached WCS-WAVE plus the cutout's own `CRPIX*W`.
5. **First deliverable (within 1 h):** `tests/test_epsf_skip.py`. Fetch the full and truncated cutouts of 2 exposures of the same detector at different positions, and assert λ agrees within 1 nm. Report the pass/fail result. If it fails, implement the full-download fallback path.
6. `resolver.py`: coordinate parser (sexagesimal/decimal), Sesame (follow redirects, parse XML), SIMBAD TAP `ident` fallback, and built-in targets (SCIENCE_REFERENCE §4).
7. `probe_endpoints.py`: a status table covering SIA (DR1, QR3), cutout, Gaia, SIMBAD (both), SkyBoT, IRSA TAP and Gemini (model list only; never print the key).

### B: Science (`backend/app/science/{flags,epochs,ephemeris,photometry,spectrum,lightcurve,astrometry,difference,render}.py`)
Read: SCIENCE_REFERENCE §2 in full, ARCHITECTURE §2. Pure functions over numpy arrays and astropy objects; **no network**. Test against the fixture FITS and synthetic Gaussian stars.
- `flags.py`: bit tables, `parse_mask_names(header)`, `hard_mask(flags)`, `contamination_bits(flags, region)`.
- `epochs.py`: `make_grid(ra, dec, fov_arcmin) -> (WCS, shape)`; `reproject_cutout(cutout, grid)`; `stack(images, variances, masks) -> (S, V_S, n)`.
- `ephemeris.py`: `predict_track(target, mjds) -> list[(ra, dec)]`. Use the differential-GCRS method from SCIENCE_REFERENCE §2.6. Unit test: the parallax amplitude for Barnard is about 0.55″.
- `photometry.py`: `measure(cutout_or_stack, ra, dec, fwhm, epsf=None) -> PhotPoint fields`. Includes the MJy/sr → µJy conversion, apcorr, saturation and flagged_frac.
- `spectrum.py`: `build_spectrum(phot_points) -> Spectrum` (102 bins, features table).
- `lightcurve.py`: `metrics(phot_points) -> LightCurve`, with the 2% systematic floor.
- `astrometry.py`: `centroid(stack, wcs, guess)` and `fit_pm(measured, catalog_parallax) -> fit`.
- `difference.py`: `zmap(S_a, V_a, S_b, V_b)`.
- `render.py`: `shared_stretch(stacks)`, `to_png(img, stretch)`, `zmap_png`, `flags_png`. Use numpy + Pillow; no matplotlib in hot paths.

### C: Frontend (`frontend/**`)
Read: ARCHITECTURE §6, API_CONTRACT (all), SUBMISSION demo script. Build against `public/demo/*/investigation.json` first.
- **Pages:** landing, investigate, embed, about. The URL state round-trips: `ra, dec, fov, name, det, mode, visit`.
- **EpochPlayer:** canvas, pixelated. Modes: animate (visits | exposures), blink A/B, diff, stack. Controls: speed, scrubber, detector picker. Overlays: track ticks, measured centroids, candidates, flags. Keyboard: space, ←/→.
- **SkyContext:** Aladin, client-only, exact pinned version. HiPS picker; Gaia/SIMBAD markers from `crossmatch`; FOV box; track polyline.
- **Plots and panels:**
  - SpectrumPlot: molecular bands shaded; saturated points hollow.
  - LightCurvePlot.
  - MotionPanel.
  - EvidencePanel: gauge, classification badge, novelty chip, item rows with ✔/✖/–/? icons and explanations.
  - CandidateList + AnnotationBox.
  - AiExplainer: disclaimer + grounding badge.
  - ProvenancePanel.
  - Status chips; progress checklist.
- **Fallback:** on any API failure within 1′ of a demo target, load the bundle and show a banner. Otherwise show a helpful error.
- **Style:** dark "observatory" theme, accessible contrast, works at phone width, no external fonts beyond one Google font.

### D: Intelligence (`backend/app/services/crossmatch.py`, `backend/app/science/{candidates,scoring}.py`, `backend/app/ai/**`, annotation queries in the DB layer)
Read: SCIENCE_REFERENCE §2.7, §3, §5; DATA_SOURCES §2, §4; ARCHITECTURE §8 (prompt injection).
- `crossmatch.py`: `gaia_cone`, `simbad_cone` (Harvard → CDS failover), `catwise_cone` (best effort, 10 s), `skybot_cone(jd)`. Every one returns a `CatalogResult` with PM-propagated separations.
- `candidates.py`: peaks, dipole pairing, recurrence clustering, rejection reasons.
- `scoring.py`: `build_evidence(...) -> Evidence`. It produces the items table, reality formula, classification rules, novelty, and a deterministic `summary` sentence template. Unit test the 8 classification paths.
- `ai/gemini.py`: REST `generateContent` with `systemInstruction`, `responseMimeType: application/json` and `responseSchema` (7 sections), plus model fallback. `grounding.py` extracts every number from the output and requires a match within relative tolerance 1% (or exact integer) against numbers in the evidence JSON, retrying once. `templates.py` is the fallback.
- Annotations: insert/list/tally functions (Opus wires them into `db.py`/routes).

### E: Ship (`backend/Dockerfile`, `render.yaml`, `frontend/vercel.json` if needed, `backend/scripts/precompute_targets.py`, `README.md`)
Starts in Phase 3.
- `precompute_targets.py` runs the pipeline for the 5 targets with FOV 3′ (WISE 0855: 3′ centred on the propagated 2026 position), writes `frontend/public/demo/{slug}/` with relative frame paths, plus `index.json`.

## 6. Feature priorities
Full table in ROADMAP.md.
- **Essential:**
  - Coordinates, names and URL params, plus embed.
  - DR1+QR3 discovery; streamed cutouts with cache.
  - Visit stacks and animation; flags overlay.
  - PM and parallax track.
  - Photometry and light curve; on-the-fly spectrum.
  - Gaia/SIMBAD identity; evidence panel.
  - Job progress; demo bundles; deploy; README.
- **High:**
  - Difference imaging; PM fit.
  - Field candidates; Gemini with grounding.
  - SkyBoT; Aladin overlays.
  - Annotations; provenance and export.
  - CatWISE; health chips.
- **Stretch:**
  - Free-parallax fit; Gaia-relative registration.
  - Cube reference spectrum; GIF export.
  - Release picker; AAVSO; PSF-wing photometry.

## 7. Scientific acceptance checks (run in Phase 4)
| Target | Expectation | Honest fallback |
|---|---|---|
| Eps Ind B | PM fit within ~5% of (+3982, −2467) mas/yr; classified *Known high-PM star*; spectrum shows a 1.6–3.3 µm CH₄ depression with a 4–5 µm peak | Report the fit with its σ, even if outside 5% |
| WISE 0855 | D5/D6 visit-stack S/N ≥ 5 at the **propagated** position; nothing at the challenge's 2010 coordinates | Label "marginal (S/N x)", which is still a valid demo of the coordinate trap |
| Barnard | Track agrees across visits; ≥2 px motion DR1→QR3; saturation warning | Track agreement only |
| R Dra | Large-amplitude change between visits in unsaturated detectors / wings; *Known variable* | Lower limits plus SIMBAD Mira identity |
| RW Aur | Variability metrics reported; *Known variable* (SIMBAD TT*/Or*) | Same |
| Empty field (e.g. RA 150.0, Dec +2.2) | Zero *unexplained* candidates at reality ≥ 70 | Tighten thresholds; document |

## 8. Risks and fallbacks
| Risk | Likelihood | Mitigation |
|---|---|---|
| IRSA SIA/cutout 502s during the demo | High | Retries, per-collection isolation, disk cache, demo bundles, warm up before judging |
| ePSF-skip λ test fails | Medium | Full cutouts with `MAX_EXPOSURES=60`; drop the exposure-level animation for visit stacks only |
| Render free tier too small or slow (reprojection memory, cold starts) | Medium | Starter plan; small FOV default 3′; health ping on landing; bundles |
| Saturation ruins photometry for 3 of 5 targets | Certain | Flag-aware lower limits; evidence says so; long-λ detectors; lean on identity and track |
| WISE 0855 undetected | Medium | D5/D6 stacks; "marginal" label; the coordinate-trap story still lands |
| CDS outage continues | Ongoing | Harvard SIMBAD mirror first; Sesame via the IDIA redirect; built-in targets |
| Gemini quota exhaustion | Low–Med | Cache per investigation; template fallback |
| Aladin npm build issues in Next.js | Low–Med | Dynamic import `ssr:false`; script-tag fallback from pinned jsdelivr |
| Scope creep | High | Phase gates and the cut order in §4 |

## 9. Definition of done (submission)
- The public URL handles a random coordinate live and all 5 targets (live or fallback).
- Each target shows animation, track, spectrum, light curve, evidence and provenance.
- At least one AI explanation passes the grounding check.
- The README contains run instructions, screenshots, data credits and the AI disclosure.
- SUBMISSION.md checklist is complete, and no secret appears in git.
