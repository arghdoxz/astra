# ASTRA — Data Sources (verified endpoints)

Every external service ASTRA touches, with exact queries, live-check results, CORS behaviour and fallbacks.
**Status legend:** ✅ VERIFIED live (date) · ⚠️ partially verified / flaky · ❓ unverified — check before relying on it.

> Windows dev note: system `curl` may fail TLS revocation checks — use `curl --ssl-no-revoke`. Python `httpx` is unaffected.

---

## 1. SPHEREx at IRSA

### 1.1 Releases — which data to use
| Release | Content | Use? |
|---|---|---|
| QR1 | Jul 2025 → retired Feb 2026 | ❌ gone |
| QR2 | Oct 2025 weekly; superseded; not searchable via SIA2 | ❌ never mix with DR1/QR3 (calibration changed) |
| **DR1** | Nov 2026; Surveys 1+2 (≈ May 2025 – May 2026) reprocessed; adds All-Sky Cube | ✅ primary |
| **QR3** | Weekly from Sep 2026; Surveys 3+4 (from ≈ May 2026), same pipeline/calibration as DR1 | ✅ primary (extends the time baseline) |

Official guidance (IRSA data-releases page): *"Together, DR1 and QR3 supersede QR2. Use DR1 and QR3 for new work."*
Combined DR1+QR3 gives a ~1.3+ year baseline with ~6-month full-sky cadence (≥3 visits per position, many more near the ecliptic poles).

SIA2 collections ✅ (docs): `spherex_dr1`, `spherex_qr3` (Wide survey, **default**), `spherex_dr1_deep`, `spherex_qr3_deep` (Deep fields near ecliptic poles), `spherex_dr1_cube` (All-Sky Cube).
Configure via env `SPHEREX_COLLECTIONS=spherex_dr1,spherex_qr3` → adding a future release = editing one env var (challenge requirement: "easy to update").

### 1.2 SIA2 image search ✅ (2026-11-14)
```
GET https://irsa.ipac.caltech.edu/SIA?COLLECTION=spherex_dr1&POS=circle+{ra}+{dec}+{radius_deg}&RESPONSEFORMAT=VOTABLE&MAXREC={n}
```
- Returns `application/x-votable+xml`, ~15 KB per row. Parse with `astropy.io.votable.parse`.
- Use a tiny radius (0.001°) — we want exposures *containing* the point; each exposure is 3.5°×3.5°.
- One row = one detector image of one exposure (6 rows per exposure, D1..D6).
- **No `Access-Control-Allow-Origin`** → must be proxied by the backend.
- ⚠️ Intermittent `502 Proxy Error` observed (DR1 query failed once, succeeded a minute later). Retry 3× with exponential backoff (1 s, 3 s, 9 s); query collections independently so one failure does not kill the other.
- ⚠️ **2026-11-15: multi-hour DR1 SIA outage** (`HTTP 502` on every DR1 query while QR3 answered). ASTRA's response: only successful SIA results are cached (24 h), so a retry re-queries; if no exposures are found **and** a collection failed, the job fails with `irsa_unavailable` ("coverage is unknown") rather than `no_coverage`; with partial results a warning names the failed collection. Targets with only a QR3 visit then come out `insufficient_data` (one visit) until DR1 is back.

Columns returned (✅ live): `s_ra, s_dec, facility_name, instrument_name, dataproduct_subtype, calib_level, dataproduct_type, energy_bandpassname, energy_emband, obs_id, s_resolution, em_min, em_max, em_res_power, proposal_title, access_url, access_format, access_estsize, t_exptime, s_region, obs_collection, obs_intent, algorithm_name, …, target_name, obs_release_date, s_xel1, s_xel2, s_pixel_scale, t_min, t_max, obs_publisher_did, s_fov, cloud_access, …`

Sample row (✅ Barnard field, DR1):
| column | value |
|---|---|
| energy_bandpassname | `SPHEREx-D6` |
| obs_id | `2025W33_2C_0321_1` |
| em_min / em_max (m) | `4.41150e-06` / `5.00960e-06` |
| em_res_power | `127.8` |
| access_url | `https://irsa.ipac.caltech.edu/ibe/data/spherex/dr1/level2/2025W33_2C/l2b-v27-2026-228/6/level2_2025W33_2C_0321_1D6_spx_l2b-v27-2026-228.fits` |
| access_estsize (KB) | `64953` (full image ≈ 65 MB — never download whole files) |
| t_min / t_max (MJD) | `60902.864715` / `60902.866047` |
| t_exptime (s) | `113.58` |
| s_region | `POLYGON ICRS 266.698 5.472 270.177 5.149 269.997 1.660 266.501 1.990 …` |
| obs_publisher_did | `ivo://irsa.ipac/spherex_dr1?2025W33_2C_0321_1/D6` (unique key; use for dedupe + cache) |
| cloud_access | `{"aws": {"bucket_name": "nasa-irsa-spherex", "key": "dr1/level2/…fits", "region": "us-east-1"}}` |

Python equivalent (docs): `Irsa.query_sia(pos=(coord, 1*u.arcsec), collection=['spherex_dr1','spherex_qr3'])`; `Irsa.list_collections(servicetype='SIA', filter='spherex')` for release auto-discovery.

### 1.3 Cutout service ✅ (2026-11-14)
```
GET {access_url}?center={ra},{dec}&size={deg}
```
- `size` in degrees (0.02° → 12×12 px; 0.05° ≈ 29 px ≈ 3′; 0.2° ≈ 117 px). GET only (HEAD → 405). No CORS header.
- Response: `application/fits`, chunked, generated on the fly. Same HDU layout as the full file:

| HDU | EXTNAME | Content |
|---|---|---|
| 0 | PRIMARY | header only (`VERSION` = pipeline version, e.g. `7.0.5`) |
| 1 | IMAGE | surface brightness, **MJy/sr**, zodi **not** subtracted |
| 2 | FLAGS | int32 bitmask (see §1.4) |
| 3 | VARIANCE | (MJy/sr)² |
| 4 | ZODI | zodiacal-light model (`ZODIMDL='KEL98_WAVESCL_V1'`), MJy/sr — subtract from IMAGE |
| 5 | EPSF | BINTABLE, 441 rows (21×21 zones; D3 uses 11×41): `BINX, BINY, XCENTER, YCENTER, XWIDTH, YWIDTH, NSTAR, NEFF_MEAN, CWAVE, CBAND, EPSF` (ePSF per zone, 33×33 stamp, oversampled ×5 per header `OVSMPX`/`OVSMPY`) |
| 6 | WCS-WAVE | BINTABLE 1 row: `X, Y, VALUES` — lookup table for per-pixel central wavelength + bandwidth |

- **Size problem:** the EPSF table (~3.86 MB) is always included, so even a 12×12 px cutout is **3.9 MB**. See ARCHITECTURE.md §"ePSF-skip streaming".
- ✅ **Streaming verified live (2026-11-15):** for Eps Ind B D6, the per-pixel λ from a streamed cutout (truncated at EPSF, EPSF/WCS-WAVE taken from the per-detector calib cache) and from the full cutout agree to **0.0000 nm** (max |Δλ|). Real HDU order is IMAGE, FLAGS, VARIANCE, **ZODI**, EPSF, WCS-WAVE, so truncation keeps ZODI.
- Key IMAGE header cards (✅): `DETECTOR`, `OBSID`, `DATE-OBS`, `MJD-OBS`, `MJD-AVG` (use for timing), `PSF_FWHM` (arcsec, ≈9.0″ for D6), `BUNIT`, celestial WCS `RA---TAN-SIP/DEC--TAN-SIP`, alternate WCS `A` (detector pixel, `LINEAR`) and **`W` = `WAVE-TAB`** (`WCSNAMEW='Approximated per-pixel wavelength and bandwidth'`, `CRPIX1W/CRPIX2W` shifted for the cutout), QA counters `HIERARCH L2 N_OVERFLOW`, `N_PERSIST`, `N_TRANSIENT`, `NBLMSRCS`, `PXSRCMSK`…
- Wavelength per pixel (from IRSA tutorial):
  ```python
  hdul = fits.open(path)
  wwcs = WCS(hdul["IMAGE"].header, fobj=hdul, key="W"); wwcs.sip = None
  wl, bw = wwcs.pixel_to_world(x, y)   # Quantity, convert .to(u.um)
  ```
  IRSA docs say the lookup table is accurate to ~1 nm and intended for visualization; for precision science use the separate Spectral WCS product (`CWAVE`/`CBAND`). ASTRA uses the lookup table (R≈40–130 means channel widths 20–40 nm ≫ 1 nm).
- A real cutout is saved as an offline test fixture: `backend/tests/fixtures/dr1_D6_barnard_0p02deg.fits` (DR1, D6, obs `2025W33_2C_0321_1`, centre 269.452, +4.6934, 0.02°).

### 1.4 FLAGS bitmask ✅ (from `MSKNxxxx` cards in the FLAGS header)
| bit | name | ASTRA treatment |
|---|---|---|
| 0 | TRANSIENT | **mask** (cosmic ray / transient hit) |
| 1 | OVERFLOW | **mask**; marks saturation → photometry = lower limit |
| 2 | SUR_ERROR | **mask** |
| 6 | NONFUNC | **mask** |
| 7 | DICHROIC | contamination (low efficiency) — report |
| 9 | MISSING_DATA | **mask** |
| 10 | HOT | **mask** |
| 11 | COLD | **mask** |
| 12 | FULLSAMPLE | informational — ignore |
| 14 | PHANMISS | contamination — report |
| 15 | NONLINEAR | **mask**; also marks saturation |
| 17 | PERSIST | contamination — report, strong artifact indicator |
| 19 | OUTLIER | **mask** |
| 20 | CROSSTALK | contamination — report |
| 21 | SOURCE | informational (pixel is on a detected source) — **never mask** |
| 22 | GHOST | contamination |
| 23 | GHOST_FPA | contamination |
| 24 | GHOST_EXT | contamination |
| 25 | STREAK | contamination (satellite/asteroid streak) |
| 26 | BLOOM | contamination (bright-star bloom) |
| 27 | SNOWBALL | contamination |
| 28 | HALO | contamination (bright-star halo) |

Parse names from the header at runtime (`MSKN0000…`) and fall back to this table. `HARD_MASK = {0,1,2,6,9,10,11,15,19}`, `CONTAMINATION = {7,14,17,20,22,23,24,25,26,27,28}`.

### 1.5 TAP ⚠️
`https://irsa.ipac.caltech.edu/TAP/sync` — tables `spherex.plane`, `spherex.artifact` (docs). During testing it **timed out (40–120 s) or returned 502** repeatedly. **Do not put TAP on the critical path.** SIA2 provides everything the pipeline needs.

### 1.6 All-Sky Cube (DR1 only)
`spherex_dr1_cube`: 102-channel, zodi-subtracted **coadd** on HEALPix tiles (12.9″ px; HDUs IMAGE, NHITS, FLAGS, SPECTRAL_CHANNELS, WCS-WAVE). **It is not time-resolved.** Use only (stretch) as a deep reference spectrum/background. No usable SPHEREx HiPS for Aladin was found.

### 1.7 Bulk alternative (not used)
Full images are mirrored on AWS S3 `s3://nasa-irsa-spherex/` (us-east-1, from `cloud_access`). Not used: whole files are 65 MB; cutouts are cheaper.

---

## 2. Cross-survey services

| Service | Endpoint | Status | CORS | Role |
|---|---|---|---|---|
| Gaia DR3 (ESA) | `https://gea.esac.esa.int/tap-server/tap/sync` | ✅ 2026-11-15 | ❌ none → proxy | PM, parallax, G mag, variability flag |
| SIMBAD (Harvard mirror) | `https://simbad.harvard.edu/simbad/sim-tap/sync` | ✅ 2026-11-15 | ✅ `*` | identity, object type |
| SIMBAD (CDS) | `https://simbad.cds.unistra.fr/simbad/sim-tap/sync` | ❌ outage page on 2026-11-15 | — | secondary in failover list |
| Sesame name resolver | `https://cds.unistra.fr/cgi-bin/nph-sesame/-oxp/SNV?{name}` (302 → `vizier.idia.ac.za` mirror) | ✅ | ❓ | name → coordinates |
| SkyBoT (IMCCE) | `https://ssp.imcce.fr/webservices/skybot/api/conesearch.php` | ✅ 2026-11-15 | ✅ `*` | known asteroids/comets at epoch |
| IRSA TAP (CatWISE2020 `catwise_2020`, AllWISE `allwise_p3as_psd`, NEOWISE `neowiser_p1bs_psd`) | `https://irsa.ipac.caltech.edu/TAP/sync` | ⚠️ timeouts | ❓ | IR proper motion / IR variability (best-effort) |

All backend calls go through `httpx` with explicit timeouts (Gaia 20 s, SIMBAD 10 s, SkyBoT 15 s, IRSA TAP 10 s) and return `{"status": "ok"|"unavailable"|"error", "service": ..., "matches": [...]}`. A dead service lowers evidence confidence; it never crashes an investigation.

### 2.1 Gaia DR3 ✅
```
GET https://gea.esac.esa.int/tap-server/tap/sync?REQUEST=doQuery&LANG=ADQL&FORMAT=csv&QUERY=<urlencoded>
SELECT source_id, ra, dec, pmra, pmdec, parallax, parallax_error, pmra_error, pmdec_error,
       phot_g_mean_mag, phot_bp_mean_mag, phot_rp_mean_mag, phot_variable_flag, ref_epoch
FROM gaiadr3.gaia_source
WHERE 1=CONTAINS(POINT('ICRS',ra,dec), CIRCLE('ICRS',{ra},{dec},{r_deg}))
```
Sample (✅): `4472831207517410816,269.4610716590444,4.676031160409681,-1.1149,-5.2526,0.25797,16.79395,NOT_AVAILABLE`.
Positions are at **epoch J2016.0** — always propagate with PM before matching to SPHEREx epochs (Barnard moves ≈ 105″ between 2016 and 2026).
For high-PM targets search radius must cover the PM offset: `r = r_match + |µ|·Δt` (cap 3′).

### 2.2 SIMBAD TAP ✅ (Harvard mirror)
```
GET {SIMBAD_TAP}?REQUEST=doQuery&LANG=ADQL&FORMAT=csv&QUERY=<urlencoded>
SELECT TOP 20 main_id, otype, ra, dec, pmra, pmdec, plx_value, rvz_redshift
FROM basic WHERE CONTAINS(POINT('ICRS',ra,dec), CIRCLE('ICRS',{ra},{dec},{r_deg}))=1
```
Sample (✅): `"UCAC4 474-068227","*",269.4565426257566,4.706951530262222`.
SIMBAD coordinates are J2000 at **epoch 2000** for most entries (propagate PM).
- ⚠️ 2026-11-15: the CDS SIMBAD TAP endpoint returned `404`; the Harvard mirror (primary) worked throughout.
Variable-type `otype` codes to treat as "known variable": `V*, Mi*, LP*, RR*, Ce*, EB*, TT*, Or*, Ae*, BY*, RS*, Ro*, Pu*, sr*, Er*, Fl*` (also `Y*O`, `Y*?`).

### 2.3 Sesame ✅
`GET https://cds.unistra.fr/cgi-bin/nph-sesame/-oxp/SNV?Barnard%27s%20star` → XML with `<jradeg>`, `<jdedeg>`, `<pmRA>`, `<pmDE>`, `<oname>`. Follow redirects. Built-in fallback coordinates for the five targets are in SCIENCE_REFERENCE.md §4.

### 2.4 SkyBoT ✅
```
GET https://ssp.imcce.fr/webservices/skybot/api/conesearch.php?-ep={JD}&-ra={deg}&-dec={deg}&-rd={radius_deg}&-mime=json&-loc=500&-output=basic
```
Returns JSON array: `{"Num":162134,"Name":"1998 TJ24","RA (hms)":"12 00 11.1435","DEC (dms)":…,"Class":"MB>Inner","VMag (mag)":20.9,"Err (arcsec)":…,"d (arcsec)":205.878,"dRA":…,"dDEC":…}`.
`-loc=500` = geocentre (SPHEREx is in LEO; the LEO–geocentre parallax matters only for very close NEOs). Query once per visit (visit mean JD), radius = cutout half-diagonal + 30″.
- ✅ **HTTP 204 with an empty body means "no objects in the cone"**, not an error; ASTRA parses it as an empty list with status `ok`.

### 2.5 IRSA TAP (best-effort) ⚠️
CatWISE2020 has `pmra, pmdec` (IR proper motions, good for brown dwarfs too faint for Gaia — e.g. WISE 0855). Verify the exact table/column names with `GET https://irsa.ipac.caltech.edu/TAP/tables` at implementation time. 10 s timeout, `status:"unavailable"` on failure.
- ⚠️ 2026-11-15: IRSA TAP returned `502` during all test runs, so CatWISE2020 evidence was `unavailable` in the validation runs (the UI and warnings say so).

---

## 3. Visualization

### Aladin Lite v3
- `https://aladin.cds.unistra.fr/AladinLite/api/v3/latest/aladin.js` returned **404 from our network** — do not depend on it.
- ✅ npm package `aladin-lite` (jsdelivr serves `aladin-lite@3.9.0-beta/dist/aladin.js`, 2.4 MB). Pin an **exact** version after `npm view aladin-lite versions`.
- Must load client-side only (`next/dynamic` with `ssr:false`, or inside `useEffect`); `await A.init` before `A.aladin(div, {survey, fov, target})`.
- HiPS IDs (✅ present in build): `CDS/P/DSS2/color`, `CDS/P/2MASS/color`, `CDS/P/allWISE/color`, `CDS/P/PanSTARRS/DR1/color-z-zg-g`. HiPS tiles from `alasky` send CORS `*`.
- ⚠️ 2026-11-15: from our network `alasky.unistra.fr`/`alaskybis.unistra.fr` did not resolve and `alasky.cds.unistra.fr/DSS/DSSColor/properties` returned 404, so HiPS-by-ID failed in the browser. **ASTRA now passes the IRSA mirror URLs** (`https://irsa.ipac.caltech.edu/data/hips/CDS/{DSS2/color,2MASS/Color,AllWISE/RGB-W4-W2-W1}`, all ✅ 200) to Aladin; the CDS ID is kept only for the external "open in Aladin" link. Pan-STARRS (no IRSA mirror) was dropped.
- API names present in build: `setImageSurvey`, `addCatalog`, `catalogFromURL`, `graphicOverlay` (check signatures in the installed version's README).

### Plotly
`react-plotly.js` + `plotly.js-dist-min` (dynamic import, `ssr:false`).

---

## 4. AI — Google Gemini ✅
- REST: `POST https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent`, header `x-goog-api-key: $GEMINI_API_KEY`.
- Models verified available to the team key (ListModels, 2026-11-15): `gemini-flash-latest`, `gemini-2.5-flash`, `gemini-2.5-pro`, `gemini-3.5-flash`, … Default `gemini-flash-latest`, fallback `gemini-2.5-flash`.
- Use `generationConfig.responseMimeType="application/json"` + `responseSchema`.
- **The key is a backend-only secret** (`backend/.env`, Render env). Never in git, docs, or `NEXT_PUBLIC_*`.

---

## 5. Python package versions (PyPI, 2026-11-15)
astropy 8.0.2 · astroquery 0.4.11 · pyvo 1.10.0 · photutils 3.1.1 · fastapi 0.162.7 (pin these; resolve the rest with `uv`). Python **3.13** (`uv venv --python 3.13`; the machine's default venv is 3.9 — too old).
