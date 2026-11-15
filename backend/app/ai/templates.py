"""Deterministic explanation sections built ONLY from the evidence payload (``prompts.build_payload``).

This is the fallback when Gemini is disabled, unavailable or fails grounding, so it must be useful on its own.
Every number printed here is copied (rounded to its stored precision) from the payload, hence always grounded.
Wording avoids claims of discovery; hypotheses are labelled as such.
"""
from __future__ import annotations

from typing import Any, Optional

from ..models import SECTION_ORDER, SECTION_TITLES, ExplanationSection, Statement

SVC_LABEL = {"gaia": "Gaia DR3", "simbad": "SIMBAD", "catwise": "CatWISE2020", "skybot": "SkyBoT"}


def _n(x: Any, nd: int = 1) -> str:
    if isinstance(x, bool):
        return str(x)
    if isinstance(x, int):
        return str(x)
    return f"{float(x):.{nd}f}"


def _item(p: dict, id_: str) -> Optional[dict]:
    return next((i for i in p["evidence"]["items"] if i["id"] == id_), None)


def _S(kind: str, text: str) -> Statement:
    return Statement(kind=kind, text=text)  # type: ignore[arg-type]


def _summary(p: dict) -> list[Statement]:
    ev = p["evidence"]
    cand = p["subject"] == "candidate"
    name = p.get("name") or ("this field" if cand else "this target")
    out = [_S("interpretation",
              f"ASTRA's rule-based classification for {name} is \"{ev['classification_label']}\" with {ev['confidence']} confidence. "
              f"This is a transparent rule tier, not a probability.")]
    if ev.get("confidence_reason"):
        out.append(_S("interpretation", ev["confidence_reason"]))
    if cand:
        c = p.get("candidate", {})
        out.append(_S("measured",
                      f"Candidate {c.get('id', '')} is a {c.get('kind', 'change')} seen at {_n(c.get('peak_z_sigma', 0.0))} σ "
                      f"in {len(c.get('detectors', []))} detector(s) and {c.get('n_visit_pairs', 0)} visit pair(s)."))
    else:
        snr = _item(p, "detection_snr")
        if snr and snr["verdict"] != "unavailable":
            out.append(_S("measured", snr["explanation"]))
        else:
            out.append(_S("missing", "No signal-to-noise measurement is available."))
        out.append(_S("measured", f"{p['n_visits']} visit(s) with data were used, built from {p['n_exposures_used']} exposures."))
    out.append(_S("interpretation",
                  f"{ev['supports']} evidence item(s) support and {ev['weakens']} weaken this result; catalog novelty is \"{ev['novelty']}\"."))
    return out


def _movement(p: dict) -> list[Statement]:
    out: list[Statement] = []
    if p["subject"] == "candidate":
        c = p.get("candidate", {})
        if c.get("kind") == "dipole" and "motion_pm_ra_mas_yr" in c:
            out.append(_S("measured",
                          f"A positive and a negative residual pair into a dipole, implying a rough motion of "
                          f"{_n(c['motion_pm_ra_mas_yr'], 0)} mas/yr in RA·cosδ and {_n(c['motion_pm_dec_mas_yr'], 0)} mas/yr in Dec."))
            out.append(_S("interpretation", "This estimate comes from one difference-image pair and is only a rough indication of movement."))
        else:
            out.append(_S("measured", "The residual is a single-signed brightness change, not a paired positive/negative dipole, so no motion is measured."))
            out.append(_S("interpretation", "A monopole points to a change in brightness at a fixed position rather than to movement."))
        return out
    a = p.get("astrometry", {})
    fit = a.get("fit")
    if fit:
        out.append(_S("measured",
                      f"The fitted proper motion is μα* = {_n(fit['pm_ra_mas_yr'])} ± {_n(fit['pm_ra_err_mas_yr'])} mas/yr and "
                      f"μδ = {_n(fit['pm_dec_mas_yr'])} ± {_n(fit['pm_dec_err_mas_yr'])} mas/yr over a {_n(fit['baseline_yr'], 2)} yr baseline "
                      f"using {fit['n_points']} epochs (χ²_red = {_n(fit['chi2_red'], 2)}, parallax mode {fit['parallax_mode']})."))
    else:
        out.append(_S("missing", "No proper-motion fit is available, so the movement could not be measured from these data."))
    cat = a.get("catalog")
    if cat:
        out.append(_S("catalog",
                      f"The catalog ({cat['source']}) gives μα* = {_n(cat['pm_ra_mas_yr'])} mas/yr, μδ = {_n(cat['pm_dec_mas_yr'])} mas/yr "
                      f"and parallax {_n(cat['parallax_mas'], 2)} mas."))
    if "consistency_sigma" in a:
        out.append(_S("measured", f"The measured motion differs from the catalog motion by {_n(a['consistency_sigma'], 2)} σ."))
    for iid in ("motion_sig", "track_agreement"):
        it = _item(p, iid)
        if it and it["verdict"] != "unavailable":
            out.append(_S("measured", it["explanation"]))
    if a.get("n_measured") and "median_residual_arcsec" in a:
        out.append(_S("measured", f"Across {a['n_measured']} measured epochs the median offset from the predicted track is {_n(a['median_residual_arcsec'], 2)} arcsec."))
    if not fit and not a.get("n_measured"):
        out.append(_S("interpretation", "Without measured centroids, ASTRA cannot confirm or rule out movement for this target."))
    return out


def _brightness(p: dict) -> list[Statement]:
    out: list[Statement] = []
    if p["subject"] == "candidate":
        c = p.get("candidate", {})
        out.append(_S("measured", f"The difference-image peak is {_n(c.get('peak_z_sigma', 0.0))} σ, seen in detector(s) {', '.join(str(d) for d in c.get('detectors', []))}."))
        it = _item(p, "recurrence")
        if it and it["verdict"] != "unavailable":
            out.append(_S("measured", it["explanation"]))
        out.append(_S("interpretation", "Whether the change is real depends on recurrence across detectors and visits, contamination flags and nearby bright stars; see Uncertainties."))
        return out
    lc = p.get("light_curve", {})
    if lc.get("n_detectors_measured"):
        out.append(_S("measured", f"{lc['n_detectors_significant']} of {lc['n_detectors_measured']} detectors with light-curve metrics meet the variability criterion "
                                  f"(χ²_red > {p['reference']['variability_chi2_red']} and amplitude > {p['reference']['variability_amp_sigma']} σ)."))
        for iid in ("variability_chi2", "variability_coherence"):
            it = _item(p, iid)
            if it and it["verdict"] != "unavailable":
                out.append(_S("measured", it["explanation"]))
        interp = ("Brightness changes that appear together in several detectors are harder to explain by instrument effects."
                  if lc.get("coherent_detectors", 0) >= 2 else
                  "No coherent multi-detector brightness change is established by these data.")
        out.append(_S("interpretation", interp))
    else:
        out.append(_S("missing", "No unsaturated light-curve metrics are available, so brightness changes cannot be assessed."))
    ph = p.get("photometry", {})
    if ph.get("n_points"):
        out.append(_S("measured", f"{ph['n_saturated']} of {ph['n_points']} photometric points are saturated and are treated as lower limits."))
    if lc:
        out.append(_S("missing", lc["period_note"]))
    return out


def _spectrum(p: dict) -> list[Statement]:
    if p["subject"] == "candidate":
        return [_S("missing", "No spectrum is built for field candidates; spectra are measured at the target position only."),
                _S("interpretation", "If this candidate is promoted to a target, its SPHEREx spectrum can be measured there.")]
    out: list[Statement] = []
    sp = p.get("spectrum", {})
    dets = [d for d in p.get("photometry", {}).get("by_detector", []) if "median_flux_ujy_unsaturated" in d]
    if dets:
        bits = []
        for d in dets:
            rng = (f" ({_n(d['wavelength_min_um'], 2)}-{_n(d['wavelength_max_um'], 2)} µm)"
                   if "wavelength_min_um" in d and "wavelength_max_um" in d else "")
            bits.append(f"detector {d['detector']}{rng}: {_n(d['median_flux_ujy_unsaturated'], 2)} µJy")
        out.append(_S("measured", "Median unsaturated flux per detector: " + "; ".join(bits) + "."))
    else:
        out.append(_S("missing", "No unsaturated per-detector fluxes are available to summarise the spectrum."))
    if sp.get("n_channels"):
        out.append(_S("measured", f"{sp.get('n_channels_with_flux_any_visit', 0)} of {sp['n_channels']} spectral channels have a flux in at least one visit; "
                                  f"{sp.get('n_gap_channels', 0)} channels have gaps."))
        src = ("the per-pixel WAVE-TAB lookup" if sp.get("wavelength_source") == "wcs_wave" else "the SIA band centre (a coarser fallback)")
        out.append(_S("measured", f"Wavelengths were taken from {src}."))
    else:
        out.append(_S("missing", "No binned spectrum is available."))
    feats = sp.get("reference_features", [])
    if feats:
        out.append(_S("catalog", "Reference molecular bands for this kind of object: " +
                      "; ".join(f"{f['species']} near {_n(f['wavelength_um'], 2)} µm" for f in feats) +
                      ". These are reference markers, not detections."))
    ph = p.get("photometry", {})
    if ph.get("n_saturated"):
        out.append(_S("interpretation", "Saturated channels give lower limits, so band depths measured there are unreliable."))
    out.append(_S("interpretation", "A single visit mixes exposures taken over days to weeks, so fast variables can distort the spectral shape."))
    return out


def _catalog(p: dict) -> list[Statement]:
    out: list[Statement] = []
    cm = p["crossmatch"]
    ref = p["reference"]
    for svc in ("gaia", "simbad", "catwise", "skybot"):
        r = cm[svc]
        lab = SVC_LABEL[svc]
        if r["status"] != "ok":
            out.append(_S("missing", f"{lab} was {r['status']}{(' (' + r['message'] + ')') if r.get('message') else ''}, so it could not be checked."))
            continue
        ms = r.get("top_matches", [])
        if not ms:
            out.append(_S("catalog", f"No {lab} source was found within the search area."))
            continue
        m = ms[0]
        txt = f"{lab}: {m['id']} lies {_n(m['sep_arcsec'], 2)} arcsec from the position"
        if m.get("epoch_propagated"):
            txt += " (catalog position propagated to the observation epoch)"
        if "mag" in m:
            txt += f", {m.get('mag_band', 'mag')} = {_n(m['mag'], 2)}"
        if "pm_ra_mas_yr" in m and "pm_dec_mas_yr" in m:
            txt += f", proper motion ({_n(m['pm_ra_mas_yr'])}, {_n(m['pm_dec_mas_yr'])}) mas/yr"
        if m.get("otype"):
            txt += f", object type {m['otype']}"
        if m.get("variable_flag"):
            txt += f", variability flag {m['variable_flag']}"
        if m.get("class"):
            txt += f", class {m['class']}"
        out.append(_S("catalog", txt + f". {r['n_matches']} source(s) in the search area."))
    out.append(_S("interpretation",
                  f"Associations use match radii of {ref['identity_match_radius_arcsec']} arcsec ({ref['catwise_match_radius_arcsec']} arcsec for CatWISE). "
                  "An association is not proof of identity; chance alignments happen, especially in crowded fields."))
    nov = p["evidence"]["novelty"]
    expl = {"catalogued": "at least one catalog source is associated with this position",
            "uncatalogued": "all queried services answered and none matched",
            "unknown": "at least one service was unavailable, so a catalog source cannot be excluded"}[nov]
    out.append(_S("interpretation", f"Catalog novelty is \"{nov}\": {expl}."))
    return out


def _uncertainties(p: dict) -> list[Statement]:
    out: list[Statement] = []
    for it in p["evidence"]["items"]:
        if it["verdict"] == "weakens":
            out.append(_S("measured", it["explanation"]))
    for it in p["evidence"]["items"]:
        if it["verdict"] == "unavailable":
            out.append(_S("missing", it["explanation"]))
    for w in p.get("warnings", []):
        out.append(_S("missing", w))
    reg = p.get("astrometry", {}).get("registration")
    ref = p["reference"]
    if reg:
        out.append(_S("measured", f"Registration check against {reg['n_stars']} Gaia stars: median offset {_n(reg['median_offset_arcsec'], 2)} arcsec, RMS {_n(reg['rms_arcsec'], 2)} arcsec. "
                                  f"WCS systematics of {ref['wcs_systematics_arcsec_low']}-{ref['wcs_systematics_arcsec_high']} arcsec are not removed."))
    else:
        out.append(_S("interpretation", f"WCS registration systematics of {ref['wcs_systematics_arcsec_low']}-{ref['wcs_systematics_arcsec_high']} arcsec are not removed and limit sub-pixel motion claims."))
    out.append(_S("interpretation", "Confidence tiers are transparent rules, not calibrated probabilities."))
    return out


_ALT = {
    "insufficient_data": [
        ("hypothesis", "With so little usable data, the apparent signal may be noise; no real change can be inferred."),
        ("hypothesis", "The target may be too faint in the selected detectors or not covered by enough visits."),
    ],
    "likely_artifact": [
        ("hypothesis", "Persistence from a bright source in an earlier exposure can leave a ghost-like residual."),
        ("hypothesis", "Optical ghosts, halos or bloom from a bright star can mimic a faint source."),
        ("hypothesis", "Saturation bleed or a satellite streak can leave localized residuals."),
        ("hypothesis", "Mis-registration between visits can leave dipole-like subtraction residuals."),
    ],
    "solar_system_object": [
        ("hypothesis", "The signal is the catalogued minor body predicted at this position and epoch; this should be verified against its ephemeris."),
        ("hypothesis", "A different, uncatalogued moving object near the same position cannot be excluded by this match alone."),
    ],
    "known_high_pm_star": [
        ("hypothesis", "The apparent movement is the catalogued star's known proper motion rather than anything unexpected."),
        ("hypothesis", "A chance alignment with a different faint source cannot be excluded by position alone."),
    ],
    "known_variable": [
        ("hypothesis", "The brightness change is the catalogued star's intrinsic variability."),
        ("hypothesis", "Calibration differences across the linear variable filter can add apparent brightness changes between visits."),
    ],
    "known_no_change": [
        ("hypothesis", "The source is stable at the measured precision; small changes below the noise cannot be excluded."),
        ("hypothesis", "The catalog association could be a chance alignment rather than the same object."),
    ],
    "no_significant_change": [
        ("hypothesis", "The source is stable at the measured precision; small changes below the noise cannot be excluded."),
        ("hypothesis", "A faint counterpart below the catalog limits could exist but is not established by these data."),
    ],
    "unexplained_needs_review": [
        ("hypothesis", "A faint or red source below the catalog depth could be responsible."),
        ("hypothesis", "An intrinsically variable star, or a solar-system body missing from the database, could explain it."),
        ("hypothesis", "An instrumental artifact (persistence, ghost, mis-registration) that is not flagged cannot be excluded."),
    ],
    "low_confidence_change": [
        ("hypothesis", "Noise or a one-off instrumental effect can produce a low-significance change."),
        ("hypothesis", "Mis-registration between visits can mimic small motion or brightness changes."),
    ],
}


def _alternatives(p: dict) -> list[Statement]:
    cls = p["evidence"]["classification"]
    out = [_S(k, t) for k, t in _ALT.get(cls, _ALT["low_confidence_change"])]
    if p["evidence"]["novelty"] == "unknown":
        out.append(_S("missing", "At least one catalog service was unavailable, so a catalogued explanation cannot be excluded."))
    it = _item(p, "contamination")
    if it and it["verdict"] == "weakens" and cls != "likely_artifact":
        out.append(_S("hypothesis", "The contamination flags near the source make an instrumental explanation plausible."))
    return out


def _next_steps(p: dict) -> list[Statement]:
    ev = p["evidence"]
    cls = ev["classification"]
    out: list[Statement] = []
    nv = _item(p, "n_visits")
    if nv and nv["verdict"] != "supports":
        out.append(_S("interpretation", "Add more visits (for example newer SPHEREx releases) to separate real change from noise."))
    down = [SVC_LABEL[s] for s in ("gaia", "simbad", "catwise", "skybot") if p["crossmatch"][s]["status"] != "ok"]
    if down:
        out.append(_S("interpretation", "Re-run the cross-match when " + ", ".join(down) + " is available."))
    steps = {
        "insufficient_data": "Check coverage and detector selection, or choose a brighter target.",
        "likely_artifact": "Inspect the flags overlay and difference frames in each detector for persistence, ghosts and halos.",
        "solar_system_object": "Compare the position with the minor-body ephemeris at the observation epoch before drawing conclusions.",
        "known_high_pm_star": "Compare the measured motion with the catalog motion over the full baseline.",
        "known_variable": "Compare against the literature light curve for this variable; do not infer a period from a few visits.",
        "known_no_change": "Confirm the catalog association by checking separations and magnitudes in an independent catalog.",
        "no_significant_change": "Keep monitoring with future releases; the current data show no significant change.",
        "unexplained_needs_review": "Have a human review the difference frames in every detector and compare with archival optical and infrared images.",
        "low_confidence_change": "Treat this as unconfirmed; look for recurrence in independent detectors and visits.",
    }
    out.append(_S("interpretation", steps.get(cls, steps["low_confidence_change"])))
    out.append(_S("interpretation", "Record your own verdict in the review queue so others can compare assessments."))
    return out


_BUILDERS = {
    "summary": _summary, "movement": _movement, "brightness": _brightness, "spectrum": _spectrum,
    "catalog_matches": _catalog, "uncertainties": _uncertainties, "alternative_explanations": _alternatives,
    "next_steps": _next_steps,
}


def template_sections(payload: dict[str, Any]) -> list[ExplanationSection]:
    """All 8 sections, in order, from the evidence payload."""
    out = []
    for key in SECTION_ORDER:
        try:
            stmts = _BUILDERS[key](payload)
        except Exception:  # a malformed payload must never break the fallback
            stmts = [_S("missing", "This section could not be generated from the available evidence.")]
        if not stmts:
            stmts = [_S("missing", "No evidence is available for this section.")]
        out.append(ExplanationSection(key=key, title=SECTION_TITLES[key], statements=stmts))  # type: ignore[arg-type]
    return out
