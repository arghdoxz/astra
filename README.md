# ASTRA — Astronomical Search & Temporal Research Assistant

**Investigate how the infrared sky changes, using real SPHEREx data.** Enter coordinates or an object name. ASTRA retrieves the SPHEREx DR1 and QR3 exposures of that spot from NASA/IPAC IRSA and animates them across the ~6-month visits. Then it:

- predicts where the target *should* be in every exposure, from its proper motion and parallax;
- measures brightness, position and a 0.75–5 µm spectrum from the calibrated images;
- compares those measurements with Gaia DR3, SIMBAD, CatWISE2020 and known Solar System objects (SkyBoT);
- grades the evidence with transparent rules: what changed, how significant it is, whether it is already known, and what might be fooling us.

Built for the **NASA Space Apps Challenge 2026, "Planet X and SPHEREx"**. ASTRA is an independent participant project. It is **not affiliated with or endorsed by NASA**, and it uses no NASA logos.

## Run it locally

Prerequisites: Python 3.13 via [uv](https://docs.astral.sh/uv/), and Node.js ≥ 20.

```bash
# backend
cd backend
cp ../.env.example .env          # optional: add GEMINI_API_KEY (never commit it)
uv sync
uv run uvicorn app.main:app --port 8000
# check http://localhost:8000/api/health

# frontend (second terminal)
cd frontend
npm install
echo NEXT_PUBLIC_API_BASE=http://localhost:8000 > .env.local
npm run dev                      # http://localhost:3000
```

Example URL: `http://localhost:3000/investigate?ra=331.04415&dec=-56.78284&name=Eps%20Ind%20B`

**Without the backend:** the five library targets fall back to precomputed bundles of **real** SPHEREx data in `frontend/public/demo/`. These are labelled on screen as a saved snapshot with their generation date. Live searches, AI explanations and annotations need the backend.

**Without a Gemini key:** the AI explainer uses a deterministic template built from the same measured evidence. It is labelled as such.

**Tests**
- `cd backend && uv run pytest` (offline unit tests)
- `uv run pytest -m live` (hits IRSA)
- `cd frontend && npx tsc --noEmit && npm run lint && npm run build`

Deployment (Render + Vercel): see [docs/DEPLOY.md](docs/DEPLOY.md).

## What is implemented

| Area | Implemented |
|---|---|
| Data | Live IRSA SIA2 discovery over DR1 and QR3; cutouts streamed through the ePSF HDU, with the ZODI model subtracted; a per-detector calibration cache (ePSF, λ map); a disk cache. Each collection is isolated, so an IRSA outage is reported as an outage, not as "no coverage". |
| Viewer | Visit stacks, single exposures, blink A/B, difference maps, an all-IR stack and detectors D1–D6. Play, step and speed controls; brightness/contrast/gamma; zoom/pan/pinch; keyboard shortcuts. Overlays for the predicted track, centroids, candidates and flags. |
| Measurements | Aperture photometry with a local annulus background and propagated variance; SNR; saturation as lower limits. A 102-bin spectrum with a channel explorer and per-visit comparison. A light curve per detector with spectral shape removed (degree ≤ 2 polynomial in λ plus grey per-visit offsets); leave-one-out outliers; relative flux. **No periods are claimed.** |
| Astrometry | Gaussian centroids; predicted-vs-observed residuals; a weighted proper-motion fit (parallax fitted freely with ≥ 4 visits and ≥ 1 yr, otherwise the catalogue value is used); a crowding check; a registration check against Gaia field stars. |
| Difference imaging | `simple` variance-weighted subtraction and `psf_matched` (single-Gaussian kernel). **Neither is ZOGY or Alard–Lupton**, and the UI says so. |
| Catalogues | Gaia DR3, SIMBAD (Harvard → CDS), CatWISE2020 (IRSA TAP, best effort) and SkyBoT. Positions are propagated to the epoch, with a user-set radius. An association is never treated as proof of identity. |
| Evidence | Rule-based classification and confidence tiers (`insufficient` / `low` / `moderate` / `strong`) with "supports" and "weakens" counts. **No AI-generated percentages.** The strongest label is "Unexplained — needs human review". |
| AI explainer | Gemini (REST, JSON schema). Statements are tagged *measured / catalog / interpretation / hypothesis / missing*. A grounding validator rejects numbers the AI was not given. Falls back to a deterministic template. |
| Citizen science | Annotations (real / artifact / known / unsure), a review queue with tallies, investigation history, and JSON/CSV/Markdown report export. |
| Sharing | All view state is kept in the URL; there is an `/embed` view and iframe code; Aladin Lite sky context comes from IRSA-mirrored HiPS. |

## What is not implemented (known limitations)

- No ZOGY/Alard–Lupton subtraction and no PSF-fitting photometry. Photometry uses apertures, and the variance is reprojected by bilinear interpolation, which is an approximation.
- No period search. Two to four visits cannot constrain periods.
- No GIF or video export of the animation.
- No user accounts: the annotation author is free text, and storage is SQLite on the server. On Render's free disk this resets on redeploy.
- Sharp spectral features (CH₄ 3.3 µm, CO 4.6 µm) can still leak into the light-curve offsets when visits sample different parts of the feature.
- The target centroid is measured on whichever stack has the highest S/N, often the all-IR stack. For very red objects (e.g. WISE 0855), a bluer neighbour can dominate it. ASTRA detects such blends against Gaia, excludes them and says so, but it cannot yet measure the target's motion from the long-wavelength detectors alone.
- Very bright targets (Barnard's Star, R Dra) saturate SPHEREx. Their motion and flux are reported as not measured or as lower limits.
- The registration check on the Barnard field reports an unexplained 8″ offset from 3 stars. It is report-only and not applied.
- Some sky positions have only one SPHEREx visit so far. ASTRA then reports `insufficient_data` instead of guessing.

The method details are in [docs/SCIENCE_REFERENCE.md](docs/SCIENCE_REFERENCE.md), and the endpoints and their quirks in [docs/DATA_SOURCES.md](docs/DATA_SOURCES.md).

## Documentation
[PROJECT_BLUEPRINT.md](PROJECT_BLUEPRINT.md) · [ARCHITECTURE](docs/ARCHITECTURE.md) · [API_CONTRACT](docs/API_CONTRACT.md) · [SCIENCE_REFERENCE](docs/SCIENCE_REFERENCE.md) · [DATA_SOURCES](docs/DATA_SOURCES.md) · [DEPLOY](docs/DEPLOY.md) · [SUBMISSION](docs/SUBMISSION.md)

## Data and credits
- SPHEREx DR1 and QR3 spectral images (NASA/JPL-Caltech), served by NASA/IPAC IRSA.
- Gaia DR3 (ESA/Gaia/DPAC).
- SIMBAD, Sesame and Aladin Lite (CDS, Strasbourg); the SIMBAD mirror is at Harvard CfA.
- HiPS sky surveys (DSS2, 2MASS, AllWISE) from the CDS, via the IRSA mirror.
- CatWISE2020 (IRSA).
- SkyBoT (IMCCE).
- Software: Astropy, photutils, reproject, NumPy, SciPy, FastAPI, Next.js, Plotly and Aladin Lite.

This research uses data from the NASA/IPAC Infrared Science Archive, operated by the Jet Propulsion Laboratory, California Institute of Technology, under contract with NASA. The project also uses the SIMBAD database operated at CDS, Strasbourg, and data from the ESA Gaia mission.

## AI disclosure
- **In the product:** the optional explainer calls Google Gemini. It receives only ASTRA's measured evidence and catalogue results. Its output is validated, and any number it was not given is rejected. All measurements, classifications and confidence tiers come from deterministic code, not from the AI.
- **In development:** the code and documentation were written with AI coding assistants, directed and reviewed by the team. All scientific results shown in the app come from running that code on real archive data.

## Honesty statement
ASTRA never claims discoveries. Simulated or placeholder data is never presented as SPHEREx data: development placeholders carry a red "not real data" banner, and demo bundles are real data labelled with their generation date.
