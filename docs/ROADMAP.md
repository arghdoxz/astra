# ASTRA — Prioritized Feature Roadmap

Effort is in agent-hours (wall-clock with parallel agents is lower). Score is Scientific value / Uniqueness / Reliability / Demo impact, each 1–3.

## ESSENTIAL (the demo fails without these)
| # | Feature | Owner | Effort | Score | Done when |
|---|---|---|---|---|---|
| E1 | Coordinate/name input + URL params (`/investigate?ra=&dec=&fov=`) + `/embed` | C | 1.5 | 2/2/3/3 | Shareable URL reproduces the view |
| E2 | SIA2 discovery (DR1+QR3), retries, dedupe, visits | A | 1.5 | 3/1/3/2 | Barnard returns ≥3 visits |
| E3 | Streaming ePSF-skip cutouts + disk cache + calib cache (+ λ verification test) | A | 2.5 | 2/3/3/2 | 100 cutouts in under 60 s cold |
| E4 | Common-grid reprojection + inverse-variance visit stacks + PNG render (shared stretch) | B | 2 | 3/2/3/3 | Blink of Eps Ind B shows displacement |
| E5 | EpochPlayer: animate visits/exposures, blink, detector picker, flag overlay | C | 3 | 2/2/3/3 | Smooth playback, flags toggle |
| E6 | Predicted PM + parallax track overlay (fixes the WISE 0855 coordinate trap) | B | 1.5 | 3/3/3/3 | Track ticks land on the source in each visit |
| E7 | Aperture photometry (µJy, saturation, flags) + light curve | B | 2 | 3/2/2/3 | R Dra light curve with saturation markers |
| E8 | On-the-fly spectrum (λ from WCS-W, 102 bins, molecular bands) | B | 2 | 3/3/2/3 | Eps Ind B spectrum shows the CH₄ region |
| E9 | Gaia + SIMBAD cross-match (PM-propagated, failover) | D | 1.5 | 3/2/2/2 | Barnard identified as known high-PM star |
| E10 | Evidence panel + reality score + classification for the target | D+C | 2.5 | 3/3/3/3 | All 5 targets classified with readable reasons |
| E11 | Investigation job API + progress UI | Opus+C | 2 | 1/1/3/2 | Stage checklist updates live |
| E12 | Demo bundles for 5 targets + automatic fallback | E | 1.5 | 1/1/3/3 | Works with backend stopped |
| E13 | Deploy (Render + Vercel) + README | E | 1.5 | 1/1/3/3 | Public URLs work |

## HIGH PRIORITY (where we win)
| # | Feature | Owner | Effort | Score |
|---|---|---|---|---|
| H1 | Difference imaging (Z-maps) in the player | B+C | 1.5 | 3/2/2/3 |
| H2 | Centroid astrometry + PM fit vs catalog (Motion panel) | B | 2 | 3/3/2/3 |
| H3 | Field candidate finder (dipoles/monopoles, recurrence, rejection) + per-candidate evidence | D | 3 | 3/3/2/3 |
| H4 | Gemini explanation + grounding validator + template fallback | D | 2 | 2/3/2/3 |
| H5 | SkyBoT solar-system check per visit | D | 0.75 | 3/2/3/2 |
| H6 | Aladin context: HiPS picker, Gaia/SIMBAD markers, FOV box, track | C | 2 | 2/2/2/3 |
| H7 | Human verification annotations + tally | D+C | 1.5 | 2/3/3/2 |
| H8 | Provenance panel (obs_ids, versions, services) + JSON/CSV report export | C | 1 | 3/2/3/2 |
| H9 | CatWISE2020 PM cross-match (best-effort) | D | 0.75 | 3/2/1/1 |
| H10 | `probe_endpoints.py` + `/api/health` service chips | A | 0.75 | 1/1/3/2 |

## STRETCH (only after H is solid)
- S1: Free-parallax astrometric fit when there are at least 4 visits.
- S2: Gaia-relative frame registration to remove the 0.1–0.3″ WCS systematics.
- S3: All-Sky Cube deep reference spectrum overlay.
- S4: GIF/WebM export of the animation.
- S5: Release auto-discovery: `Irsa.list_collections(filter='spherex')` drives a UI release picker.
- S6: AAVSO light-curve overlay for R Dra and RW Aur, with phase folding at P = 245.6 d for R Dra.
- S7: Saturated-star photometry from PSF wings, using the ePSF fit outside the masked core.
- S8: Persistent disk for annotations.

## Explicitly out of scope
User accounts, a general-purpose database server, microservices, full-image downloads, QR2 data, any "discovery" claims.
