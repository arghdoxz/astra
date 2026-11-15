# ASTRA — Space Apps 2026 submission pack

Challenge: **Planet X and SPHEREx**. ASTRA is an independent team project. It is not affiliated with or endorsed by NASA. Do not use NASA logos in the video, slides or app.

## 1. Project summary (≤ 250 words)

**ASTRA turns SPHEREx's 102-colour infrared sky into investigations anyone can run, honestly.**

Enter coordinates or a name. ASTRA retrieves the SPHEREx DR1 and QR3 exposures of that position from IRSA. It stacks them into ~6-month visits, and you can play, blink and difference them like a time-lapse. Using catalogue proper motion and parallax, ASTRA predicts where the target *should* be in every exposure. It measures position, brightness and a 0.75–5 µm spectrum from the calibrated images. It then checks the result against Gaia DR3, SIMBAD, CatWISE and known asteroids.

Every conclusion comes from transparent rules: each evidence item shows its value, threshold and reason. The confidence tiers are *insufficient / low / moderate / strong*, never invented percentages. ASTRA also reports what can fool it: saturation, SPHEREx artifact flags, blends with neighbouring stars, and archive outages. An optional AI assistant explains the evidence in plain language. Every sentence is tagged as measured, catalogue, interpretation, hypothesis or missing, and a validator rejects any number the AI was not given. Citizen scientists can record verdicts and export reports.

ASTRA never announces discoveries. The strongest thing it can say is "Unexplained — needs human review."

## 2. Detailed description

**What it does.** For any sky position, ASTRA runs these steps:
1. Discover SPHEREx exposures with IRSA SIA2. DR1 and QR3 are queried independently, so an outage is reported as an outage, not as "no coverage".
2. Download small cutouts (streamed through the ePSF extension; zodiacal model subtracted).
3. Reproject and stack them per visit and detector.
4. Measure aperture photometry, centroids, a spectrum and a light curve with the spectral shape removed.
5. Fit proper motion, with parallax fitted when ≥ 4 visits span ≥ 1 yr.
6. Cross-match against catalogues propagated to the observation epoch.
7. Find field candidates in difference maps.
8. Grade the evidence.

**Why it matters.** Planet X-style searches are searches for faint, moving, cold objects, and they are dominated by false positives. ASTRA shows the complete chain from pixels to conclusion, including the reasons a signal might *not* be real. That makes it useful as both a teaching tool and a vetting tool.

**Validation on the five library targets.** All five use real data; full results are in §6.

**Built with:** Python 3.13, FastAPI, Astropy, photutils, reproject, NumPy and SciPy (backend); Next.js, TypeScript, Tailwind, Plotly and Aladin Lite (frontend); Google Gemini (optional explainer).

## 3. Technical documentation
- [README](../README.md): run instructions, what is and is not implemented, credits.
- [ARCHITECTURE](ARCHITECTURE.md), [API_CONTRACT](API_CONTRACT.md), [SCIENCE_REFERENCE](SCIENCE_REFERENCE.md) (every formula and threshold), [DATA_SOURCES](DATA_SOURCES.md) (verified endpoints and their quirks), [DEPLOY](DEPLOY.md).

## 4. 30-second demo script
| t | Screen | Voice-over / caption |
|---|---|---|
| 0–4 s | Landing page, then type "WISE 0855" | "SPHEREx maps the whole sky in 102 infrared colours every six months." |
| 4–11 s | Investigate: frames playing, predicted track ticking across the field | "ASTRA pulls every SPHEREx exposure of a spot and predicts where each star *should* be." |
| 11–18 s | Eps Ind B: blink A/B, Motion panel with measured vs catalogue proper motion | "Here it measures a brown dwarf's motion and checks it against Gaia." |
| 18–25 s | Evidence panel: items with supports/weakens and a blend or saturation warning | "Every conclusion shows its evidence, including what could be fooling us." |
| 25–30 s | AI explainer with statement tags; Share link | "Real data. Real measurements. Honest uncertainty." |

Record from the deployed app (or locally) with captions on and no copyrighted music.

## 5. Slide outline (7 slides)
1. **Title.** ASTRA: an honest time-domain explorer for SPHEREx. Team names. Footer: "Independent project — not endorsed by NASA".
2. **Problem.** Moving and cold-object searches drown in false positives: saturation, artifacts, blends, stale coordinates. The challenge's WISE 0855 coordinates are ~2 arcmin out of date.
3. **What ASTRA does.** Pipeline diagram: IRSA SIA2 → cutouts → visit stacks → measurements → catalogues → evidence → explainer.
4. **Live example: Eps Ind B.** Animation still, measured vs catalogue proper motion, residuals.
5. **Honesty by design.** Evidence items with thresholds; confidence tiers; "motion not measured" for saturated stars; the blend warning on WISE 0855; outage handling.
6. **Citizen science and sharing.** Annotations, review queue, report export, URL and embed.
7. **Limits and next steps.** No ZOGY or PSF photometry yet, few visits, no period search. Next: PSF-fit photometry and more SPHEREx releases. Credits and AI disclosure.

## 6. Validation results (real data, bundles in `frontend/public/demo/`)
Generated 2026-11-15 with 3′ fields and 160 exposures per target. CatWISE (IRSA TAP) was unavailable during these runs.

| Target | Visits | ASTRA result | Matches expectation? |
|---|---|---|---|
| Eps Ind B | 4 (DR1 + QR3) | Known high-PM star, **moderate**. Measured µ = 3742 ± 301 / −2276 ± 294 mas/yr vs catalogue 3982 / −2467 (consistent); free-fit parallax 361 ± 170 mas vs 271 (consistent). Track residuals ≤ 0.7″. No variability in any detector (χ²ᵣ ≤ 4). | Yes. The best motion test, as planned. |
| WISE 0855-0714 | 3 | Known high-PM star (**motion not measured**), **low**. The challenge coordinates are recognised as the ~2010 position and propagated. A Gaia star (G = 16.3) dominates the all-IR centroid, so all visits are flagged as blended and excluded from the motion fit. D5/D6 (4–5 µm) fluxes are steady at ~0.5 mJy, consistent with W2 ≈ 14. | Partly. Coordinate propagation and honesty hold, but ASTRA cannot yet measure its motion; that needs D5/D6-only centroids or PSF fitting. |
| Barnard's Star | 4 | Known high-PM star (**motion not measured**), **low**. Saturated in 99% of exposures, so no centroid is usable. Identity: SIMBAD "Barnard's star". | Yes on honesty, no on a measurement. Saturation was expected. |
| RW Aur | 3 | Known variable, **low**. One detector varies significantly (12.6σ); the others are mostly saturated (91%). | Plausible. RW Aur is a known dimming T Tauri star, but a single-detector change is weak evidence and is reported as such. |
| R Dra | 3 | **Insufficient data**. The core is saturated in 99% of exposures and hard-masked, so there is no usable flux. | Honest. R Dra (K ≈ 2) is far beyond SPHEREx saturation, so ASTRA does not guess. |
| Control field (150.0, +2.2) | live | Known source, no change, **moderate** (earlier live run). | Yes. |

## 7. Data, resources and attributions
- **NASA SPHEREx DR1 and QR3** spectral images (NASA/JPL-Caltech), via the NASA/IPAC Infrared Science Archive (IRSA): SIA2 and cutout services.
- **ESA Gaia DR3** (Gaia Archive TAP).
- **SIMBAD** and **Sesame** (CDS, Strasbourg; SIMBAD TAP mirror at Harvard CfA).
- **Aladin Lite v3** (CDS), with DSS2/2MASS/AllWISE HiPS served from the IRSA mirror.
- **CatWISE2020** (IRSA TAP, best effort).
- **SkyBoT** (IMCCE).
- Open-source software: Astropy, photutils, reproject, NumPy, SciPy, FastAPI, Pydantic, httpx, Next.js, React, Tailwind CSS, Plotly.js.
- **Acknowledgement text:** "This research has made use of the NASA/IPAC Infrared Science Archive, which is funded by NASA and operated by the California Institute of Technology; the SIMBAD database, operated at CDS, Strasbourg, France; and data from the ESA mission Gaia, processed by the Gaia DPAC."

## 8. AI disclosure
- **Inside ASTRA:** Google Gemini (`gemini-2.5-flash` / `gemini-flash-latest`) writes optional plain-language explanations.
  - It receives only ASTRA's computed evidence.
  - Every statement must carry a kind tag, and a validator rejects any number not present in the input.
  - With no key, or on any failure, a deterministic template is used, and the UI labels which source produced the text.
  - No measurement, classification or confidence tier is generated by AI.
- **During development:** the code and documentation were produced with AI coding assistants, directed, reviewed and tested by the team. The scientific results come from running that code on real archive data; none were written by hand or by an AI.

## 9. Submission checklist
- [ ] Repo pushed to GitHub (public), with no secrets: `git grep -nE "AIza[0-9A-Za-z_-]{30}"` prints nothing, and `backend/.env` is not tracked.
- [ ] Backend deployed on Render and `/api/health` answers. Frontend deployed on Vercel with `NEXT_PUBLIC_API_BASE` set. See DEPLOY.md.
- [ ] The app opens in an incognito window, and all five target cards load (live or real-data snapshot).
- [ ] 30-second video recorded (§4); slides made (§5).
- [ ] Summary (§1), description (§2), resources (§7) and AI disclosure (§8) pasted into the Space Apps project page.
- [ ] Team members and roles listed.
- [ ] Rotate the Gemini API key after judging (it was shared during development).
