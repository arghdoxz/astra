"""Evidence items, confidence tier, classification and novelty (SCIENCE_REFERENCE section 5).

ASTRA outputs NO percentage score: the tier is a transparent rule set (first match wins) and `confidence_reason`
names the rule. Everything here is deterministic; the explanation sentences contain the numbers they describe.
A catalog association is never presented as proof of identity.
"""
from __future__ import annotations

import math
from typing import Any, Optional

from ..core_types import EvidenceInput
from ..models import CatalogMatch, Evidence, EvidenceItem

# identity-association radii (arcsec), SCIENCE_REFERENCE section 3
IDENTITY_RADIUS_ARCSEC = {"gaia": 3.0, "simbad": 3.0, "catwise": 5.0}
SKYBOT_ASSOC_ARCSEC = 15.0        # 10 arcsec + 3 x typical SkyBoT positional error
SIG_CHANGE_SIGMA = 5.0
PM_CONSISTENT_SIGMA = 3.0
HIGH_PM_MAS_YR = 100.0
BRIGHT_NEIGHBOR_ARCMIN = 2.0
SEVERE_CONTAM = ("PERSIST", "GHOST", "HALO", "BLOOM", "STREAK")

VARIABLE_OTYPES = frozenset({
    "V*", "Mi*", "LP*", "RR*", "Ce*", "EB*", "TT*", "Or*", "Ae*", "BY*", "RS*", "Ro*", "Pu*", "sr*", "Er*", "Fl*",
    "Y*O", "Y*?",
})

CLASS_LABELS = {
    "insufficient_data": "Insufficient data",
    "likely_artifact": "Likely artifact",
    "solar_system_object": "Solar-system object",
    "known_high_pm_star": "Known high-proper-motion star",
    "known_variable": "Known variable",
    "known_no_change": "Known source, no significant change",
    "no_significant_change": "No significant change detected",
    "unexplained_needs_review": "Unexplained — needs human review",
    "low_confidence_change": "Low-confidence change",
}


def is_variable_otype(otype: Optional[str]) -> bool:
    return bool(otype) and otype.strip() in VARIABLE_OTYPES


def identity_matches(cm: Any) -> list[tuple[str, CatalogMatch]]:
    """Gaia/SIMBAD/CatWISE matches within the identity radii, nearest first."""
    out: list[tuple[str, CatalogMatch]] = []
    if cm is None:
        return out
    for svc, rad in IDENTITY_RADIUS_ARCSEC.items():
        res = getattr(cm, svc, None)
        if res is None or res.status != "ok":
            continue
        out.extend((svc, m) for m in res.matches if m.sep_arcsec <= rad)
    # SIMBAD lists exoplanets at their host's position; they are never the infrared source, so rank them last.
    out.sort(key=lambda t: ((t[1].otype or "").strip().startswith("Pl"), t[1].sep_arcsec))
    return out


def skybot_matches(cm: Any) -> list[CatalogMatch]:
    res = getattr(cm, "skybot", None) if cm is not None else None
    if res is None or res.status != "ok":
        return []
    return sorted((m for m in res.matches if m.sep_arcsec <= SKYBOT_ASSOC_ARCSEC), key=lambda m: m.sep_arcsec)


def compute_novelty(cm: Any) -> str:
    """catalogued > unknown > uncatalogued (a match wins even if another service was down)."""
    if cm is None:
        return "unknown"
    if identity_matches(cm) or skybot_matches(cm):
        return "catalogued"
    if any(getattr(cm, s).status != "ok" for s in ("gaia", "simbad", "catwise", "skybot")):
        return "unknown"
    return "uncatalogued"


def _n(x: float, nd: int = 2) -> str:
    return f"{x:.{nd}f}"


def _item(id_: str, label: str, value: Any, unit: Optional[str], threshold: str, verdict: str, expl: str,
          prov: dict[str, list[str]]) -> EvidenceItem:
    return EvidenceItem(id=id_, label=label, value=value, unit=unit, threshold=threshold, verdict=verdict,  # type: ignore[arg-type]
                        explanation=expl, provenance=prov.get(id_) or None)


def build_evidence(inp: EvidenceInput) -> Evidence:
    prov = inp.provenance or {}
    cand = inp.subject == "candidate"
    what = "candidate" if cand else "target"
    items: list[EvidenceItem] = []
    cm = inp.crossmatch

    # ---- detection_snr
    snr = inp.snr
    if snr is None:
        items.append(_item("detection_snr", "Detection signal-to-noise", None, "sigma", "supports >= 10, weakens < 5",
                           "unavailable", f"No signal-to-noise measurement is available for this {what}.", prov))
    else:
        v = "supports" if snr >= 10 else ("weakens" if snr < 5 else "neutral")
        word = {"supports": "a clear detection", "weakens": "a weak or marginal detection", "neutral": "a moderate detection"}[v]
        items.append(_item("detection_snr", "Detection signal-to-noise", round(snr, 2), "sigma", "supports >= 10, weakens < 5", v,
                           f"The maximum signal-to-noise at the {what} position is {_n(snr)} sigma, {word}.", prov))

    # ---- motion_sig
    if inp.motion_sig is None:
        items.append(_item("motion_sig", "Motion significance", None, "sigma", "supports >= 5", "unavailable",
                           "No proper-motion fit is available, so motion significance cannot be assessed.", prov))
    else:
        v = "supports" if inp.motion_sig >= 5 else "neutral"
        pm = ""
        if inp.pm_measured is not None:
            pm = (f" Measured proper motion: mu_alpha* = {_n(inp.pm_measured[0], 1)} mas/yr, "
                  f"mu_delta = {_n(inp.pm_measured[1], 1)} mas/yr.")
        tail = "motion is significant." if v == "supports" else "motion is below the 5 sigma significance threshold."
        items.append(_item("motion_sig", "Motion significance", round(inp.motion_sig, 2), "sigma", "supports >= 5", v,
                           f"|mu|/sigma_mu = {_n(inp.motion_sig)}; {tail}{pm}", prov))

    # ---- catalog_pm_consistency
    c = inp.catalog_pm_consistency
    if c is None:
        items.append(_item("catalog_pm_consistency", "Catalog proper-motion consistency", None, "sigma",
                           "supports < 3, weakens >= 3", "unavailable",
                           "No catalog proper motion was available to compare with the measured motion.", prov))
    else:
        v = "supports" if c < 3 else "weakens"
        tail = "consistent with" if v == "supports" else "inconsistent with"
        items.append(_item("catalog_pm_consistency", "Catalog proper-motion consistency", round(c, 2), "sigma",
                           "supports < 3, weakens >= 3", v,
                           f"The measured proper motion differs from the catalog value by {_n(c)} sigma, {tail} the catalog.", prov))

    # ---- track_agreement
    t = inp.track_agreement
    if t is None:
        items.append(_item("track_agreement", "Agreement with predicted track", None, "sigma", "supports < 3, weakens >= 3",
                           "unavailable", "No predicted track comparison is available (no catalog motion or no centroids).", prov))
    else:
        v = "supports" if t < 3 else "weakens"
        tail = "agree with" if v == "supports" else "deviate from"
        items.append(_item("track_agreement", "Agreement with predicted track", round(t, 2), "sigma", "supports < 3, weakens >= 3", v,
                           f"The median offset of measured centroids from the predicted track is {_n(t)} sigma; positions {tail} the prediction.", prov))

    # ---- variability_chi2 / coherence
    nsig = inp.variability_significant_dets
    if inp.max_chi2_red is None:
        items.append(_item("variability_chi2", "Variability (chi-square)", None, None,
                           "chi2_red > 5 and amplitude > 5 sigma in >= 2 detectors", "unavailable",
                           "No unsaturated light-curve metrics are available, so variability cannot be assessed.", prov))
        items.append(_item("variability_coherence", "Variability coherence across detectors", None, "detectors",
                           "supports >= 2, weakens 1", "unavailable",
                           "Coherence across detectors cannot be assessed without light-curve metrics.", prov))
    else:
        amp = f" with a largest amplitude of {_n(inp.amp_sigma)} sigma" if inp.amp_sigma is not None else ""
        v = "supports" if nsig >= 2 else "neutral"
        tail = ("meets the criterion (chi2_red > 5 and amplitude > 5 sigma in at least 2 detectors)." if v == "supports"
                else "does not meet the criterion (chi2_red > 5 and amplitude > 5 sigma in at least 2 detectors).")
        items.append(_item("variability_chi2", "Variability (chi-square)", round(inp.max_chi2_red, 2), "chi2_red",
                           "chi2_red > 5 and amplitude > 5 sigma in >= 2 detectors", v,
                           f"The largest reduced chi-square is {_n(inp.max_chi2_red)}{amp}; {nsig} detector(s) are significant, which {tail}", prov))
        k = inp.coherent_detectors
        vc = "supports" if k >= 2 else ("weakens" if k == 1 else "neutral")
        tc = {"supports": "changes move together across wavelength, which argues against an artifact.",
              "weakens": "a change in a single detector only is more likely instrumental.",
              "neutral": "no detector shows a coherent change."}[vc]
        items.append(_item("variability_coherence", "Variability coherence across detectors", k, "detectors",
                           "supports >= 2, weakens 1", vc, f"{k} detector(s) change in the same sense; {tc}", prov))

    # ---- recurrence (candidates)
    if cand or inp.recurrence is not None:
        r = inp.recurrence
        if r is None:
            items.append(_item("recurrence", "Recurrence (detector x visit pair)", None, "detections", "supports >= 2, weakens 1",
                               "unavailable", "Recurrence was not computed.", prov))
        else:
            v = "supports" if r >= 2 else "weakens"
            tail = ("recurs, which argues against a single-frame artifact." if v == "supports"
                    else "appears in only one detector and visit pair, so it is low-confidence.")
            items.append(_item("recurrence", "Recurrence (detector x visit pair)", r, "detections", "supports >= 2, weakens 1", v,
                               f"The signal is detected in {r} detector x visit-pair combination(s); it {tail}", prov))

    # ---- flagged_fraction
    ff = inp.flagged_frac
    if ff is None:
        items.append(_item("flagged_fraction", "Flagged pixel fraction", None, "fraction", "supports < 0.1, weakens > 0.3",
                           "unavailable", "The fraction of flagged aperture pixels is not available.", prov))
    else:
        v = "supports" if ff < 0.1 else ("weakens" if ff > 0.3 else "neutral")
        items.append(_item("flagged_fraction", "Flagged pixel fraction", round(ff, 3), "fraction", "supports < 0.1, weakens > 0.3", v,
                           f"{_n(ff, 3)} of the aperture pixels are hard-masked by quality flags.", prov))

    # ---- saturation
    sf = inp.saturated_frac
    if sf is None:
        items.append(_item("saturation", "Saturated measurements", None, "fraction", "supports = 0, weakens > 0.5", "unavailable",
                           "Saturation fraction is not available.", prov))
    else:
        v = "supports" if sf == 0 else ("weakens" if sf > 0.5 else "neutral")
        tail = ("no measurement is saturated." if v == "supports" else
                "most fluxes are lower limits and centroids may be biased." if v == "weakens" else
                "some fluxes are lower limits.")
        items.append(_item("saturation", "Saturated measurements", round(sf, 3), "fraction", "supports = 0, weakens > 0.5", v,
                           f"{_n(sf, 3)} of the measurements are saturated; {tail}", prov))

    # ---- contamination
    if not inp.contamination:
        items.append(_item("contamination", "Contamination flags near source", "none", None, "weakens if any contamination flag",
                           "supports", "No contamination flags (persistence, ghosts, halo, bloom, streak) were found near the source.", prov))
    else:
        names = ", ".join(sorted(set(inp.contamination)))
        items.append(_item("contamination", "Contamination flags near source", names, None, "weakens if any contamination flag",
                           "weakens", f"Contamination flags were found near the source: {names}. These are common artifact causes.", prov))

    # ---- bright_neighbor
    bn = inp.bright_neighbor_arcmin
    if bn is None:
        items.append(_item("bright_neighbor", "Nearest bright (G < 8) star", None, "arcmin", "supports > 2, weakens < 2", "unavailable",
                           "Gaia was unavailable, so bright neighbours that cause halos and subtraction residuals could not be checked.", prov))
    elif math.isinf(bn):
        items.append(_item("bright_neighbor", "Nearest bright (G < 8) star", "none within 2 arcmin", None, "supports > 2, weakens < 2",
                           "supports", "No Gaia star brighter than G = 8 lies within 2 arcmin.", prov))
    else:
        v = "supports" if bn >= BRIGHT_NEIGHBOR_ARCMIN else "weakens"
        tail = "far enough to avoid halo and bloom." if v == "supports" else "close enough to cause halo, bloom or subtraction residuals."
        items.append(_item("bright_neighbor", "Nearest bright (G < 8) star", round(bn, 2), "arcmin", "supports > 2, weakens < 2", v,
                           f"The nearest star brighter than G = 8 is {_n(bn)} arcmin away, {tail}", prov))

    # ---- n_visits
    nv = inp.n_visits
    v = "supports" if nv >= 3 else ("weakens" if nv < 2 else "neutral")
    items.append(_item("n_visits", "Visits with data", nv, "visits", "supports >= 3, weakens < 2", v,
                       f"{nv} visit(s) have usable data; " + ("enough epochs for a time-domain comparison." if v == "supports"
                                                              else "too few epochs to separate change from noise." if v == "weakens"
                                                              else "a two-epoch comparison is possible but limited."), prov))

    # ---- catalog_identity
    ids = identity_matches(cm)
    svc_status = {s: getattr(cm, s).status for s in ("gaia", "simbad", "catwise")} if cm is not None else {}
    down = [s for s, st in svc_status.items() if st != "ok"]
    if cm is None:
        items.append(_item("catalog_identity", "Catalog association", None, None, "affects novelty, not reality", "unavailable",
                           "No catalog cross-match was performed.", prov))
    elif ids:
        svc, m = ids[0]
        rad = IDENTITY_RADIUS_ARCSEC[svc]
        extra = f" ({len(ids) - 1} more association(s) within the radii)" if len(ids) > 1 else ""
        items.append(_item("catalog_identity", "Catalog association", m.id, "arcsec", "affects novelty, not reality", "neutral",
                           f"Nearest catalog association: {m.id} ({svc}) at {_n(m.sep_arcsec)} arcsec, within the {_n(rad, 1)} arcsec match radius{extra}. "
                           "This is an association, not proof of identity.", prov))
    elif down and len(down) == len(svc_status):
        items.append(_item("catalog_identity", "Catalog association", None, None, "affects novelty, not reality", "unavailable",
                           "Gaia, SIMBAD and CatWISE were all unavailable, so no association could be checked.", prov))
    else:
        tail = f" ({', '.join(down)} unavailable)" if down else ""
        items.append(_item("catalog_identity", "Catalog association", "none", None, "affects novelty, not reality", "neutral",
                           f"No Gaia, SIMBAD or CatWISE source lies within the match radii (3 arcsec; 5 arcsec for CatWISE){tail}.", prov))

    # ---- solar_system
    sk = skybot_matches(cm)
    sk_status = getattr(cm, "skybot").status if cm is not None else "unavailable"
    if sk:
        m = sk[0]
        vtxt = f", V = {_n(m.mag, 1)}" if m.mag is not None else ""
        items.append(_item("solar_system", "Solar-system object match", m.id, "arcsec", "classification only", "neutral",
                           f"A known minor body, {m.id} ({m.class_ or 'class unknown'}{vtxt}), is predicted {_n(m.sep_arcsec)} arcsec from the position at the observation epoch.", prov))
    elif sk_status != "ok":
        items.append(_item("solar_system", "Solar-system object match", None, None, "classification only", "unavailable",
                           "SkyBoT was unavailable, so a solar-system object could not be excluded.", prov))
    else:
        items.append(_item("solar_system", "Solar-system object match", "none", None, "classification only", "neutral",
                           "SkyBoT reports no known minor body near the position at the observation epoch.", prov))

    supports = sum(1 for i in items if i.verdict == "supports")
    weakens = sum(1 for i in items if i.verdict == "weakens")

    # ---- derived quantities
    rec = inp.recurrence if inp.recurrence is not None else (0 if cand else inp.n_visits)
    sig_inputs = [x for x in (inp.motion_sig, inp.amp_sigma, snr if cand else None) if x is not None]
    change_sigma = max(sig_inputs) if sig_inputs else None
    sig_change = change_sigma is not None and change_sigma >= SIG_CHANGE_SIGMA
    novelty = compute_novelty(cm)

    # ---- confidence tier (first rule wins)
    if inp.n_visits < 2 or snr is None or snr < 3:
        conf = "insufficient"
        if snr is None:
            reason = "Rule 1 (insufficient): no usable measurement."
        elif snr < 3:
            reason = f"Rule 1 (insufficient): signal-to-noise {_n(snr)} is below 3."
        else:
            reason = f"Rule 1 (insufficient): only {inp.n_visits} visit(s) with data (need at least 2)."
    elif snr >= 10 and ((rec >= 2) if cand else (inp.n_visits >= 3)) and weakens == 0:
        conf = "strong"
        reason = (f"Rule 2 (strong): signal-to-noise {_n(snr)} >= 10, "
                  + (f"recurrence {rec} >= 2" if cand else f"{inp.n_visits} visits >= 3") + ", and no evidence item weakens it.")
    elif snr >= 5 and weakens <= 1:
        conf = "moderate"
        reason = f"Rule 3 (moderate): signal-to-noise {_n(snr)} >= 5 and {weakens} evidence item(s) weaken it (at most 1)."
    else:
        conf = "low"
        reason = f"Rule 4 (low): signal-to-noise {_n(snr)} with {weakens} weakening item(s) did not meet the moderate or strong rules."

    # ---- classification (first rule wins)
    matched = bool(ids)
    top_pm = inp.catalog_pm_total
    if top_pm is None:
        for _svc, m in ids:
            if m.pm_ra is not None and m.pm_dec is not None:
                top_pm = math.hypot(m.pm_ra, m.pm_dec)
                break
    cat_variable = inp.catalog_variable or any(
        (m.variable_flag or "").upper() == "VARIABLE" or is_variable_otype(m.otype) for _s, m in ids)
    pm_consistent = (inp.track_agreement is not None and inp.track_agreement < 3) or (
        inp.catalog_pm_consistency is not None and inp.catalog_pm_consistency < PM_CONSISTENT_SIGMA)
    # Motion untested: no track comparison and no catalog-PM comparison (e.g. every centroid saturated or blended).
    # A catalogued high-PM star is then still the known explanation, but it is not confirmed by our measurement.
    pm_untested = (not cand) and inp.track_agreement is None and inp.catalog_pm_consistency is None
    var_sig = nsig >= 2
    label_extra = ""
    if inp.n_visits < 2 or snr is None or snr < 3:
        cls = "insufficient_data"
    elif inp.contamination and rec < 2:
        cls = "likely_artifact"
    elif sk:
        cls = "solar_system_object"
    elif matched and top_pm is not None and top_pm > HIGH_PM_MAS_YR and pm_consistent:
        cls = "known_high_pm_star"
    elif matched and top_pm is not None and top_pm > HIGH_PM_MAS_YR and pm_untested:
        cls = "known_high_pm_star"
        label_extra = " (motion not measured)"
        if conf in ("moderate", "strong"):
            conf = "low"
        reason = (reason.rstrip(".") + "; capped at low because the catalogued motion could not be checked "
                  "(no unsaturated, unblended centroids).")
    elif matched and (var_sig or cat_variable):
        cls = "known_variable"
    elif matched and not sig_change:
        cls = "known_no_change"
    elif sig_change and conf in ("moderate", "strong") and not matched:
        cls = "unexplained_needs_review"
        if novelty == "unknown":
            label_extra = " (catalog check incomplete)"
    elif not matched and not sig_change and snr >= 3:
        cls = "no_significant_change"
        if novelty == "unknown":
            label_extra = " (catalog check incomplete)"
    else:
        cls = "low_confidence_change"
    label = CLASS_LABELS[cls]
    if cls == "solar_system_object":
        m = sk[0]
        label = f"Solar-system object: {m.id}" + (f" ({m.class_}" + (f", V = {_n(m.mag, 1)}" if m.mag is not None else "") + ")" if m.class_ else "")
    label += label_extra

    # ---- deterministic summary
    nm = inp.name or ("This candidate" if cand else "This target")
    sig_txt = (f"The largest change significance is {_n(change_sigma)} sigma." if change_sigma is not None
               else "No change significance could be computed.")
    summary = (f"{nm}: {label}, with {conf} confidence ({reason.rstrip('.')}). "
               f"{supports} evidence item(s) support and {weakens} weaken this result. {sig_txt} "
               f"Catalog novelty: {novelty}. Catalog associations are not proof of identity.")
    return Evidence(confidence=conf, confidence_reason=reason, supports=supports, weakens=weakens,  # type: ignore[arg-type]
                    classification=cls, classification_label=label, novelty=novelty,  # type: ignore[arg-type]
                    items=items, summary=summary)
