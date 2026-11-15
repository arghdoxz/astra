# ASTRA — Scientific Reference

The scientific rules ASTRA implements. Every number shown to a user must come from a computation described here. The AI layer may only *explain* these numbers; it never produces new ones.

---

## 1. SPHEREx in one page
- **Mission:** NASA SPHEREx, launched March 2025, sun-synchronous LEO. Survey operations began May 2025. It maps the **whole sky every ~6 months** in **102 spectral channels, 0.75–5.0 µm**.
- **How spectra are built:** each of the 6 detectors sits behind a **linear variable filter (LVF)**. Wavelength therefore changes across the detector. A single exposure gives each sky position *one* wavelength per detector. The full spectrum builds up as the sky drifts across the LVF over successive exposures in a survey pass.
- **Pixel scale:** 6.15″, 2040×2040 px per detector, 3.5°×3.5° field. PSF FWHM is ~6–9″, under-sampled at short wavelengths.

| Detector | λ range (µm) | R = λ/Δλ | Channel width ≈ |
|---|---|---|---|
| D1 | 0.75–1.09 | 39 | 23 nm |
| D2 | 1.10–1.62 | 41 | 33 nm |
| D3 | 1.63–2.41 | 41 | 49 nm |
| D4 | 2.42–3.82 | 35 | 89 nm |
| D5 | 3.83–4.41 | 112 | 37 nm |
| D6 | 4.42–5.00 | 128 | 37 nm |

- **Data used:** Level-2 calibrated spectral images (DR1 and QR3). Their units are MJy/sr. Zodiacal light is modelled in the ZODI HDU but is **not subtracted**.
- **Not a time series:** the All-Sky Cube is a co-add across all DR1 epochs and **must not** be used for time-domain claims.
- **Sensitivity:** the pre-launch 5σ point-source depth per channel per visit is roughly AB 16.6–18 at 3.8–5 µm. It is zodi-limited (arXiv 2505.24856). The full-survey co-add is about 1 mag deeper.

## 2. Measurements

### 2.1 Pre-processing (per cutout)
1. **Background (resolved 2026-11-15):** real cutouts are ordered PRIMARY, IMAGE, FLAGS, VARIANCE, **ZODI**, EPSF, WCS-WAVE (verified on the fixture and live). The streaming downloader stops at EPSF, so ZODI is kept in both modes. Use `I = IMAGE − ZODI − median_sigclip(IMAGE − ZODI)` for display/stacks and a **local annulus background** for photometry (falls back to median-only if ZODI is missing). `V = VARIANCE`.
2. Keep `raw_flags = FLAGS` unmodified. Set the mask to true where `FLAGS & HARD_MASK` (bits 0, 1, 2, 6, 9, 10, 11, 15, 19); masked pixels are set to NaN. SOURCE (bit 21) is informational and never masked.
3. Compute `contam = FLAGS & CONTAMINATION` (bits 7, 14, 17, 20, 22–28). It is kept for evidence and never silently dropped.
4. **Time:** use `MJD-AVG` from the IMAGE header, cross-checked against the SIA `t_min` and `t_max`.

### 2.2 Visit grouping and stacking
- **Visit:** a set of exposures with no internal gap of more than 30 days. One visit corresponds to one ~6-month survey pass over the position.
- **Stack** per (visit, detector):
  - Reproject every exposure onto a common north-up TAN grid centred on the request, at 6.15″ px (`reproject.reproject_interp`). The variance is reprojected the same way.
  - Combine with an inverse-variance-weighted mean: `S = Σ(I/V) / Σ(1/V)` and `V_S = 1/Σ(1/V)`, ignoring NaNs.
- **"All-IR" stack:** the same weighted mean across all detectors in one visit. It is used only for display and detection, never for photometry, because it mixes wavelengths.
- **Display stretch:** use asinh with **one shared (vmin, vmax) for all visits** of the same detector. Compute it from the 1st and 99.5th percentiles of the median stack. Without shared limits, blinking would fake variability.

### 2.3 Photometry
- **Flux conversion:** the pixel solid angle comes from the WCS, `Ω_pix = proj_plane_pixel_area(wcs)` in deg², converted to sr. Nominal value: `(6.15″)² = 8.89×10⁻¹⁰ sr`.
  `F_ν[µJy] = Σ_aperture I[MJy/sr] × 10¹² × Ω_pix`, so 1 MJy/sr in one pixel ≈ 889 µJy.
- **Aperture photometry** (photutils):
  - Circular aperture with r = 1.0 × FWHM, using `PSF_FWHM` from the header or the D-dependent default.
  - Background from the median of an annulus between 2.0 and 3.5 × FWHM, with masked pixels excluded.
  - Error (resolved, both terms in µJy²): `σ_F² = (10¹² Ω)² · [ Σ_ap V + N_ap² · σ_bkg² / N_ann ]`, where σ_bkg is the sigma-clipped std of the annulus in MJy/sr.
- **Aperture correction:** take the cached ePSF of the zone nearest the source (EPSF table: XCENTER/YCENTER, ×5 oversampled per header `OVSMPX`; 33×33 stamps). The correction is `f_ap = Σ ePSF inside r / Σ ePSF`, giving `F_total = F_ap / f_ap`. If no ePSF is cached, use `f_ap` from a Gaussian with that FWHM and record `apcorr_method:"gaussian"`.
- **AB magnitude:** `m_AB = 23.9 − 2.5 log10(F_ν[µJy])` (equivalent to `−2.5 log10(F_ν / 3631 Jy)`); null for F ≤ 0.
- **Saturation:** a measurement is `saturated = true` if any pixel within the aperture has bit 1 or 15 **in `raw_flags`** (those pixels are NaN after hard masking, so saturation must be read before masking). The flux from remaining pixels is a lower limit. Saturated fluxes are lower limits and are excluded from the variability χ² and from the spectrum fit. The UI shows them as hollow markers. Barnard's Star, RW Aur and R Dra are expected to be mostly saturated.
- **Quality:**
  - `flagged_frac` is the fraction of aperture pixels hard-masked by bits **other than** the saturation bits 1 and 15. If it exceeds 0.3, the point is rejected (flux null). Saturated points are kept as lower limits.
  - `contamination_bits` lists the names of contamination bits found in the aperture.

### 2.4 Spectrum ("on-the-fly", challenge extra credit)
- Each exposure × detector gives one point (λ, F_ν). λ is read from the alternate WCS `W` (WAVE-TAB) at the source's pixel position, and the bandwidth comes from the same lookup.
- A visit across D1–D6 yields a 0.75–5 µm spectrum. Bin onto the 102-channel grid (17 channels per detector, at equal log-λ steps within each detector's range). Each bin takes the weighted mean of its points.
- Plot each visit as its own series. Differences between visits are spectral variability, which is meaningful for R Dra and RW Aur.
- **Molecular feature guides** (shown as reference bands; not claims):

| Species | Bands (µm) | Expected in |
|---|---|---|
| H₂O | 1.4, 1.9, 2.7 | M dwarfs (Barnard), Miras (R Dra), brown dwarfs |
| CH₄ | 1.65, 2.2, 3.3 | T and Y dwarfs (Eps Ind Bb, WISE 0855) |
| CO | 2.3 (overtone), 4.6 (fundamental) | cool stars, Miras, YSO discs, Y dwarfs |
| CO₂ | 4.3 | Y/T dwarfs |
| NH₃ | ~3.0 | Y dwarfs |
| H₂O ice | 3.0 | young stellar objects / dusty envelopes |
| Brα / Paα/β | 4.05 / 1.87, 1.28 | accretion in T Tauri stars (RW Aur) — unresolved at R≈40 except Brα in D5 |

### 2.5 Light curve and variability
- Plot F_ν against MJD per detector, with unsaturated points only.
- **Why not a constant model:** within one detector every exposure sits at a different wavelength (D1 alone spans 0.75–1.09 µm), so raw fluxes mix spectral shape with time variability. On live Eps Ind B a constant-flux χ² gave χ²_red ≈ 1000 for a non-variable brown dwarf. **Do not compare raw fluxes across λ.**
- **Model per detector (implemented 2026-11-15):** weighted least squares in ln F with `ln F_i = P(λ_i) + δ_visit(i)`, where P is a polynomial (degree ≤ 2, limited so ≥1 dof remains) shared by all visits and δ is a grey per-visit offset (δ = 0 for the earliest visit). σ_lnF = σ_F/F with the 2% floor. Offset errors are inflated by √max(1, χ²_full/dof) so spectral-shape misfit cannot masquerade as variability.
- **Metrics per detector:**
  - `chi2_red` = (χ²(P only) − χ²(P + δ)) / (n_visits − 1), divided by the misfit factor; ≈ 1 for a constant source
  - `amp_sigma = (δ_max − δ_min) / σ(δ_max − δ_min)` (full covariance)
  - `frac_amp = exp(δ_max − δ_min) − 1`
  - direction = sign(δ_latest − δ_earliest)
- **Systematic floor:** add 2% of the flux in quadrature to every error. This covers calibration and the LVF position. Without it, bright stars look variable.
- **Variability is significant** when `χ²_red > 5` **and** `amp_sigma > 5` in at least 2 detectors moving in the same direction. Moving together across wavelength is the strongest evidence against artifacts.
- **Outliers:** the point with the largest residual is refitted leave-one-out; it is an `outlier` if the refit model misses it by > 5σ (σ_lnF × misfit factor). Repeated up to 25% of the detector's points. A point that is alone in its visit is never flagged (it cannot be told from variability). Outliers are shown but excluded from the metrics.
- **Limitation:** sharp features narrower than the polynomial can follow (e.g. CH₄ 3.3 µm, CO 4.6 µm in cool dwarfs) can still leak into δ when visits sample different parts of the feature; the misfit inflation reduces but does not remove this.
- **Relative flux:** `rel_flux = F / median(F of the same λ bin in the reference visit)`; the reference visit is the earliest visit with ≥3 unsaturated points.
- **Periods:** ASTRA never fits or claims a period. With a handful of survey visits a period is unconstrained; `period_note` says so and cites the literature period only as catalog context.
- **Caveat:** a single visit's points come from different wavelengths per detector. Compare like with like by comparing the same detector across visits, and use the mean of points within ±1 channel.

### 2.6 Astrometry and motion
- **Predicted track** (`ephemeris.py`):
  ```python
  c = SkyCoord(ra=ra*u.deg, dec=dec*u.deg, pm_ra_cosdec=pmra*u.mas/u.yr, pm_dec=pmdec*u.mas/u.yr,
               distance=Distance(parallax=max(plx,1e-3)*u.mas), obstime=Time(ref_epoch, format="jyear"))
  p = c.apply_space_motion(new_obstime=Time(mjd, format="mjd"))
  apparent = p.transform_to(GCRS(obstime=Time(mjd, format="mjd")))   # adds annual parallax (geocentric observer)
  ```
  Here `ref_epoch` is 2016.0 for Gaia DR3 and 2000.0 for most SIMBAD entries. SPHEREx observes at about 90° solar elongation, which maximizes the parallax displacement. Use GCRS, then convert to ICRS-like offsets for plotting.
  - **Known GCRS caveat:** GCRS includes aberration (~20″), which is common to all stars in the field and is removed by the SPHEREx WCS solution. To get the parallax-only track, compute the GCRS position of the target **minus** the GCRS position of a zero-parallax, zero-PM point at the same coordinates. Add that differential offset to the PM-propagated ICRS position.
- **Measured positions:**
  - Measure a centroid per (visit, stack). Use `photutils.centroids.centroid_2dg` in a 5×5 px box around the predicted position, and only on unsaturated stacks with SNR ≥ 10. Convert to RA/Dec with the stack WCS.
  - Error per axis: `σ_pos ≈ FWHM / (2.355 × SNR)` in quadrature with a **0.3″ systematic floor**, which covers WCS registration. Blackhole 102 found about 0.1″ seasonal systematics.
- **Fit:** subtract the predicted parallax term (catalog parallax), then fit `Δα* = μα* Δt + c₁`, `Δδ = μδ Δt + c₂` by weighted least squares. That gives μ ± σ and `χ²_red`. With ≥4 measured epochs **and** baseline ≥ 1 yr, also fit parallax freely (`Δα* = μα*Δt + ϖ·Pα(t) + c₁`, same for δ, with parallax factors from the differential GCRS offset per unit parallax) and report it as `parallax_mode:"fitted"`; otherwise `fixed_catalog` (or `none` if no catalog parallax).
- **Residuals:** every measured epoch reports observed − predicted (RA·cosδ, Dec) in arcsec.
- **Crowding:** a measurement is `crowded` if another peak > 20% of the target's peak lies within 2 × FWHM. Crowded or saturated epochs are excluded from the fit and shown hollow.
- **Blend check (Gaia):** at SPHEREx resolution a neighbour within ~1 PSF FWHM (median stack `PSF_FWHM`, ≈6–9″) cannot be separated by peak-finding. If a Gaia DR3 source (epoch-propagated, > 2″ from the predicted position so the target's own entry is ignored) lies within that radius of the predicted target position in a visit, the visit's centroid is marked `crowded`, excluded from the PM fit and track comparison, and a warning names the neighbour. Found live on WISE 0855: a Gaia star 7.2″ away dominated the all-IR centroid (Y dwarf is dark below 3 µm), producing a spurious 21σ PM disagreement and short-λ 'variability' as the dwarf moved onto the star.
- **Registration check:** centroid up to 10 unsaturated Gaia stars (G 10–16) per stack, propagate Gaia to the epoch, and report the median and RMS offset. Gaia is propagated to the epoch of the measured (first) visit stack and stars within 30″ of the target are skipped (halo/bloom of bright targets). This is reported only; frames are not re-registered (stretch goal).
- **Motion significance:** `|μ| / σ_μ`.
- **Catalog consistency:** `|μ_meas − μ_cat| / sqrt(σ_meas² + σ_cat²) < 3`.
- **Scale check:** expected motion per 6 months is 0.84 px (Barnard), 0.66 px (WISE 0855) and 0.38 px (Eps Ind B). This is sub-pixel, so blinking alone will not show it convincingly. Always show the track overlay and the centroid fit. With DR1+QR3 (≥1.3 yr) Barnard moves ≥2 px.

### 2.7 Difference imaging and candidate detection
- Take a visit pair (a, b) on the same detector and the same reprojected grid. Two methods, both honestly labelled:
  - `simple`: `D = S_b − S_a`, `Z = D / sqrt(V_a + V_b)`, masks OR-combined (NaN), no flux scaling unless the median ratio of bright unsaturated common pixels differs from 1 by >5% (then reported and applied).
  - `psf_matched`: Gaussian approximation. With per-stack effective FWHM (median header `PSF_FWHM`), convolve the sharper stack with a Gaussian of `σ_k = sqrt(σ_broad² − σ_sharp²)` (in pixels); convolve its variance with the kernel squared (normalised kernel², i.e. `V' = V ⊛ k²`). This is **not** ZOGY or Alard–Lupton: the real SPHEREx PSF is under-sampled and non-Gaussian.
  Imperfect subtraction around bright stars is handled by the bright-star penalty.
- **Peaks:** `photutils.detection.find_peaks(|Z|, threshold=5, box_size=5)`, run on each (pair, detector).
- **Pairing:** a positive and a negative peak within `max(3 px, 1.5 × |μ_max| Δt)` form a **dipole**, meaning a mover candidate. The motion vector is the negative→positive offset divided by Δt. Unpaired peaks are **monopoles**, meaning a brightness change.
- **Recurrence:** cluster detections within 2 px across detectors and visit pairs. A candidate needs **recurrence in ≥2 detectors or ≥2 visit pairs**. A single-detector, single-pair detection is reported only as "low-confidence".
- **Rejection, recorded as evidence and never silently deleted:**
  - Any contamination bit (PERSIST, GHOST*, HALO, BLOOM, STREAK, CROSSTALK, SNOWBALL) in a 3 px radius in either epoch.
  - A Gaia star with G < 8 within 2′, which causes halo, bloom and subtraction residuals. Eps Ind A is about 402″ from Eps Ind B.
  - Fewer than 5 good pixels.

## 3. Cross-survey identification
- Propagate catalog positions to the SPHEREx visit epoch before matching, using `apply_space_motion` with catalog PM and parallax. Match radius: 3″ for Gaia/SIMBAD, 5″ for CatWISE.
- **SkyBoT:** a known minor body within `10″ + 3×positional error` at the visit JD gives the "solar-system object" identification.
- Report every service's status. If Gaia was unavailable, the evidence says so explicitly.

## 4. The five demonstration targets
Coordinates are ICRS. Gaia/SIMBAD positions are at J2016.0 or J2000.0 as noted. Use these as **built-in fallbacks** when resolvers fail.

| Target | RA (deg) | Dec (deg) | Pos. epoch | µα* (mas/yr) | µδ (mas/yr) | ϖ (mas) | SpT | K (mag) | Role |
|---|---|---|---|---|---|---|---|---|---|
| Barnard's Star | 269.45208 | +4.69336 | J2000 (SIMBAD) | −801.6 | +10362.4 | 546.98 | M4V | 4.52 | fastest proper motion; parallax; **saturated** |
| Eps Ind B (Ba+Bb) | 331.04415 | −56.78284 | J2000 (SIMBAD) | +3982.0 | −2466.8 | 270.66 | T1+T6 | 11.21 | best motion test: unsaturated, CH₄ spectrum; Eps Ind A (K≈2) 402″ away |
| WISE 0855−0714 | 133.81891 | −7.24705 | J2000 (SIMBAD) | −8123.7 | +673.2 | 439.0 | Y2 (SIMBAD; Y4 in some refs) | W2≈13.9 Vega | coldest brown dwarf; only in stacked D5/D6 |
| RW Aur | 76.95653 | +30.40144 | J2000 | +7.2 | −20.3 | ~6–7 (Gaia DR3 — UNVERIFIED, query live; Hipparcos 15.4 is unreliable) | K1-5e TTS | 7.02 | variability, dust dimming, IR excess; **saturated in most frames** |
| R Dra | 248.16761 | +66.75498 | J2000 | −20.6 | +6.1 | 1.25 | M Mira | 2.23 | Mira, P ≈ 245 d, large IR amplitude; near the NEP so dense coverage; **saturated** |

- **WISE 0855 coordinate warning:** the challenge text gives `08h55m10.831s −07°14′42.53″` = (133.79513, −7.24515). That is the ~2010 WISE-era position. By 2026 the source is about **130″ (~21 px) away**. ASTRA must propagate the proper motion, or the cutout centres on empty sky. This is a strong teaching moment for the demo.
- **Expected outcomes, stated honestly:**
  - **Barnard:** moves ~2 px over DR1+QR3. The core is saturated, so centroids may be biased. Report a reduced-confidence measured PM and lean on track agreement.
  - **Eps Ind B:** clean centroids in D3–D6. The PM fit should land within ~5% of the catalog (Blackhole 102 got 3940±25 / −2441±21). Spectrum: CH₄ absorption at 1.65, 2.2 and 3.3 µm, plus a 4–5 µm peak.
  - **WISE 0855:** an S/N ~5–20 detection only in D5/D6 visit stacks (W2 ≈ 17.2 AB). Undetectable below 3 µm (J ≈ 25). Label it "marginal" when S/N < 5.
  - **RW Aur:** variability across visits is plausible (deep dimming episodes). Saturation limits this, so use the unsaturated long-λ detectors and PSF wings.
  - **R Dra:** large-amplitude pulsation. Visits ~6 months apart sample different phases of the ~245 d period. Expect changing H₂O/CO band depths. Mostly saturated, so present as lower limits and flag-aware.

## 5. Evidence scoring
Each target or candidate produces `evidence.items[]`. Every item carries its numeric value, threshold, verdict (`supports` / `weakens` / `neutral`), a plain-language explanation, and provenance (obs_ids).

| Item id | Quantity | Supports if | Weakens if |
|---|---|---|---|
| `detection_snr` | max stack SNR | ≥ 10 | < 5 |
| `motion_sig` | \|µ\|/σ_µ | ≥ 5 | — (neutral below) |
| `catalog_pm_consistency` | Δµ/σ | < 3 | ≥ 3 |
| `track_agreement` | median centroid offset from predicted track / σ | < 3 | ≥ 3 |
| `variability_chi2` | χ²_red (unsaturated) | > 5 in ≥ 2 det | — |
| `variability_coherence` | n detectors changing in the same sense | ≥ 2 | 1 |
| `recurrence` | n (detector × visit-pair) detections | ≥ 2 | 1 |
| `flagged_fraction` | fraction of hard-masked aperture pixels | < 0.1 | > 0.3 |
| `saturation` | fraction of saturated measurements | 0 | > 0.5 |
| `contamination` | contamination bits near source | none | any of PERSIST/GHOST*/HALO/BLOOM/STREAK |
| `bright_neighbor` | nearest G < 8 star | > 2′ | < 2′ |
| `n_visits` | visits with data | ≥ 3 | < 2 |
| `catalog_identity` | Gaia/SIMBAD/CatWISE match | — (affects novelty, not reality) | — |
| `solar_system` | SkyBoT match | — (classification) | — |

**Confidence tier (replaces the earlier logistic "reality score", 2026-11-15).** ASTRA does not output a percentage, because no calibrated probability exists. The tier describes how well the evidence supports the *classification*, by transparent rules (first match wins); `confidence_reason` names the rule:
1. `insufficient`: n_visits < 2, or SNR < 3, or no usable measurement.
2. `strong`: SNR ≥ 10 **and** (n_visits ≥ 3 for a target / recurrence ≥ 2 for a field candidate) **and** zero `weakens` items.
3. `moderate`: SNR ≥ 5 **and** at most one `weakens` item.
4. `low`: everything else.
`supports` / `weakens` count items by verdict. `change_sigma = max(motion_sig, amp_sigma)`; a **significant change** means `change_sigma ≥ 5`. "Motion consistent" means `catalog_pm_consistency < 3`.

**Classification** (deterministic, first rule that matches wins):
1. `n_visits < 2` or `SNR < 3` → **Insufficient data**
2. contamination present **and** recurrence < 2 → **Likely artifact**
3. SkyBoT match → **Solar-system object** (name, class, V mag)
4. catalog match **and** catalog |µ| > 100 mas/yr **and** (track_agreement < 3σ or motion consistent) → **Known high-proper-motion star**
   - 4b. same, but motion **untested** (no track comparison and no catalog-PM comparison, e.g. every centroid saturated or blended) → **Known high-proper-motion star (motion not measured)**, confidence capped at `low`. A measured contradiction (consistency ≥ 3σ) still blocks rule 4.
5. catalog match **and** (variability significant **or** Gaia `phot_variable_flag = VARIABLE` **or** SIMBAD variable otype) → **Known variable**
6. catalog match and no significant change → **Known source, no significant change**
7. significant change **and** confidence ∈ {moderate, strong} **and no** catalog match → **Unexplained — needs human review**
8. no catalog match, no significant change, SNR ≥ 3 → **No significant change detected** (`no_significant_change`)
9. otherwise → **Low-confidence change**

**Novelty:**
- `catalogued` if any identity match exists.
- `uncatalogued` if all identity services answered and none matched.
- `unknown` if any service was unavailable.
- Precedence: `catalogued` > `unknown` > `uncatalogued` (a match wins even if another service was down).
- A catalog association is reported with its separation and match radius; it is **never** presented as proof of identity.

**Language rule:** ASTRA never outputs "discovery", "new planet" or "Planet X". The strongest statement allowed is "Unexplained — needs human review", with the reasons it was not explained.

## 6. Known limitations (shown in the UI's "About the science" panel)
- Centroids and photometry are biased for saturated stars. Flags identify those cases, but no full saturated-PSF fit is done.
- Difference imaging is either simple variance-weighted subtraction or a single-Gaussian PSF match; neither is ZOGY / Alard–Lupton.
- Variance is reprojected with bilinear interpolation, which correlates neighbouring pixels; stack S/N is therefore slightly optimistic.
- The ZODI model plus a per-cutout median are subtracted; residual zodi/background structure on arcminute scales is handled only by the local photometry annulus.
- WCS registration systematics of about 0.1–0.3″ are not removed (Gaia-relative alignment is a stretch goal).
- The wavelength lookup table is approximate to ~1 nm, well below a channel width.
- Spectra from one visit mix exposures taken over days to weeks, so fast variables can distort the spectral shape.
- QR3 is a quick release. Its calibration matches DR1 per IRSA, but it may be reprocessed later.
- Confidence tiers are transparent rules, not calibrated probabilities. ASTRA claims no periods and no discoveries.
