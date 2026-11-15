import math

from app.core_types import EvidenceInput
from app.models import CatalogMatch, CatalogResult, CrossMatch
from app.science.scoring import build_evidence, compute_novelty


def cm(gaia=None, simbad=None, catwise=None, skybot=None, down=()):
    """CrossMatch where every service answered ok, except those named in ``down`` (unavailable)."""
    def res(svc, matches):
        return CatalogResult(service=svc, status="unavailable" if svc in down else "ok", matches=matches or [])
    return CrossMatch(gaia=res("gaia", gaia), simbad=res("simbad", simbad),
                      catwise=res("catwise", catwise), skybot=res("skybot", skybot))


def clean(**kw):
    """A clean target measurement; override fields per test."""
    base = dict(subject="target", snr=12.0, n_visits=3, flagged_frac=0.0, saturated_frac=0.0,
                bright_neighbor_arcmin=math.inf, crossmatch=cm())
    base.update(kw)
    return EvidenceInput(**base)


def item(ev, id_):
    return next(i for i in ev.items if i.id == id_)


# ---------------- classification: all 9 rules ----------------
def test_rule1_insufficient_data_visits():
    ev = build_evidence(clean(n_visits=1))
    assert ev.classification == "insufficient_data" and ev.confidence == "insufficient"


def test_rule1_insufficient_data_snr():
    ev = build_evidence(clean(snr=2.0))
    assert ev.classification == "insufficient_data"
    assert "Rule 1" in ev.confidence_reason


def test_rule2_likely_artifact():
    ev = build_evidence(clean(subject="candidate", recurrence=1, contamination=["PERSIST"], snr=8.0))
    assert ev.classification == "likely_artifact"
    assert item(ev, "contamination").verdict == "weakens"


def test_rule2_not_applied_when_recurring():
    ev = build_evidence(clean(subject="candidate", recurrence=3, contamination=["PERSIST"], snr=8.0))
    assert ev.classification != "likely_artifact"


def test_rule3_solar_system():
    sk = CatalogMatch(id="(162134) 1998 TJ24", ra=1, dec=1, sep_arcsec=2.0, mag=20.9, mag_band="V",
                      **{"class": "MB>Inner"})
    ev = build_evidence(clean(crossmatch=cm(skybot=[sk])))
    assert ev.classification == "solar_system_object"
    assert "1998 TJ24" in ev.classification_label and ev.novelty == "catalogued"


def test_rule4_known_high_pm_star():
    g = CatalogMatch(id="Gaia DR3 1", ra=1, dec=1, sep_arcsec=0.4, pm_ra=-801.6, pm_dec=10362.4)
    ev = build_evidence(clean(crossmatch=cm(gaia=[g]), track_agreement=1.0, snr=40))
    assert ev.classification == "known_high_pm_star"
    assert "not proof of identity" in item(ev, "catalog_identity").explanation


def test_rule4_requires_consistent_motion():
    g = CatalogMatch(id="Gaia DR3 1", ra=1, dec=1, sep_arcsec=0.4, pm_ra=-801.6, pm_dec=10362.4)
    ev = build_evidence(clean(crossmatch=cm(gaia=[g]), track_agreement=5.0, catalog_pm_consistency=6.0, snr=40))
    assert ev.classification == "known_no_change"      # matched, no significant change, motion inconsistent


def test_rule5_known_variable_gaia_flag():
    g = CatalogMatch(id="Gaia DR3 2", ra=1, dec=1, sep_arcsec=0.5, variable_flag="VARIABLE")
    assert build_evidence(clean(crossmatch=cm(gaia=[g]))).classification == "known_variable"


def test_rule5_known_variable_measured():
    g = CatalogMatch(id="Gaia DR3 2", ra=1, dec=1, sep_arcsec=0.5)
    ev = build_evidence(clean(crossmatch=cm(gaia=[g]), variability_significant_dets=3, max_chi2_red=9.0,
                              amp_sigma=12.0, coherent_detectors=3))
    assert ev.classification == "known_variable"


def test_rule5_known_variable_simbad_otype():
    s = CatalogMatch(id="R Dra", ra=1, dec=1, sep_arcsec=0.5, otype="Mi*")
    assert build_evidence(clean(crossmatch=cm(simbad=[s]))).classification == "known_variable"


def test_rule6_known_no_change():
    g = CatalogMatch(id="Gaia DR3 3", ra=1, dec=1, sep_arcsec=1.0, pm_ra=2.0, pm_dec=1.0)
    ev = build_evidence(clean(crossmatch=cm(gaia=[g])))
    assert ev.classification == "known_no_change"
    assert ev.novelty == "catalogued"


def test_rule7_unexplained_needs_review():
    ev = build_evidence(clean(motion_sig=8.0))
    assert ev.classification == "unexplained_needs_review"
    assert ev.novelty == "uncatalogued" and ev.confidence in ("moderate", "strong")
    assert "discovery" not in ev.summary.lower() and "new planet" not in ev.summary.lower()


def test_rule7_flags_incomplete_catalog_check():
    ev = build_evidence(clean(motion_sig=8.0, crossmatch=cm(down=("catwise",))))
    assert ev.classification == "unexplained_needs_review"
    assert ev.novelty == "unknown" and "incomplete" in ev.classification_label


def test_rule8_no_significant_change():
    ev = build_evidence(clean(snr=8.0, motion_sig=1.0, amp_sigma=2.0))
    assert ev.classification == "no_significant_change"


def test_rule9_low_confidence_change():
    ev = build_evidence(clean(snr=4.0, motion_sig=6.0))
    assert ev.confidence == "low"
    assert ev.classification == "low_confidence_change"


# ---------------- confidence tiers ----------------
def test_tier_insufficient():
    assert build_evidence(clean(n_visits=1)).confidence == "insufficient"
    assert build_evidence(clean(snr=None)).confidence == "insufficient"


def test_tier_strong_target():
    ev = build_evidence(clean())
    assert ev.weakens == 0 and ev.confidence == "strong" and "Rule 2" in ev.confidence_reason


def test_tier_strong_candidate_needs_recurrence():
    assert build_evidence(clean(subject="candidate", recurrence=3)).confidence == "strong"
    assert build_evidence(clean(subject="candidate", recurrence=1)).confidence != "strong"


def test_tier_moderate_one_weakening_item():
    ev = build_evidence(clean(snr=7.0, bright_neighbor_arcmin=1.0))
    assert ev.weakens == 1 and ev.confidence == "moderate" and "Rule 3" in ev.confidence_reason


def test_tier_low_two_weakening_items():
    ev = build_evidence(clean(snr=7.0, bright_neighbor_arcmin=1.0, contamination=["HALO"]))
    assert ev.weakens == 2 and ev.confidence == "low" and "Rule 4" in ev.confidence_reason


# ---------------- items / novelty ----------------
def test_unavailable_inputs_are_marked():
    ev = build_evidence(EvidenceInput(subject="target", snr=None, n_visits=3))
    for iid in ("detection_snr", "motion_sig", "catalog_identity", "bright_neighbor"):
        assert item(ev, iid).verdict == "unavailable"
    assert "Gaia was unavailable" in item(ev, "bright_neighbor").explanation


def test_item_verdicts_and_numbers_in_explanations():
    ev = build_evidence(clean(snr=12.34, motion_sig=6.5, catalog_pm_consistency=1.2, track_agreement=4.0,
                              flagged_frac=0.4, saturated_frac=0.8, n_visits=1))
    assert item(ev, "detection_snr").verdict == "supports" and "12.34" in item(ev, "detection_snr").explanation
    assert item(ev, "motion_sig").verdict == "supports"
    assert item(ev, "catalog_pm_consistency").verdict == "supports"
    assert item(ev, "track_agreement").verdict == "weakens"
    assert item(ev, "flagged_fraction").verdict == "weakens"
    assert item(ev, "saturation").verdict == "weakens"
    assert item(ev, "n_visits").verdict == "weakens"
    assert ev.supports == sum(1 for i in ev.items if i.verdict == "supports")
    assert ev.weakens == sum(1 for i in ev.items if i.verdict == "weakens")


def test_variability_items():
    ev = build_evidence(clean(variability_significant_dets=1, max_chi2_red=8.0, amp_sigma=6.0, coherent_detectors=1))
    assert item(ev, "variability_chi2").verdict == "neutral"       # full rule needs >= 2 detectors
    assert item(ev, "variability_coherence").verdict == "weakens"


def test_recurrence_only_for_candidates_or_when_given():
    assert not any(i.id == "recurrence" for i in build_evidence(clean()).items)
    assert item(build_evidence(clean(subject="candidate", recurrence=1)), "recurrence").verdict == "weakens"


def test_novelty_precedence():
    g = CatalogMatch(id="x", ra=1, dec=1, sep_arcsec=1.0)
    assert compute_novelty(cm(gaia=[g], down=("simbad",))) == "catalogued"   # a match beats an outage
    assert compute_novelty(cm(down=("gaia",))) == "unknown"
    assert compute_novelty(cm()) == "uncatalogued"
    assert compute_novelty(None) == "unknown"


def test_catalog_match_outside_identity_radius_is_not_a_match():
    far = CatalogMatch(id="Gaia DR3 9", ra=1, dec=1, sep_arcsec=20.0)
    ev = build_evidence(clean(crossmatch=cm(gaia=[far])))
    assert ev.novelty == "uncatalogued"


def test_rule4_high_pm_untested_motion_is_capped_low():
    # every centroid saturated or blended: no track comparison and no catalog-PM comparison
    g = CatalogMatch(id="Gaia DR3 1", ra=1, dec=1, sep_arcsec=0.4, pm_ra=-801.6, pm_dec=10362.4)
    ev = build_evidence(clean(crossmatch=cm(gaia=[g]), snr=40))
    assert ev.classification == "known_high_pm_star"
    assert "motion not measured" in ev.classification_label
    assert ev.confidence == "low"


def test_rule4_measured_contradiction_still_blocks_high_pm():
    g = CatalogMatch(id="Gaia DR3 1", ra=1, dec=1, sep_arcsec=0.4, pm_ra=-801.6, pm_dec=10362.4)
    ev = build_evidence(clean(crossmatch=cm(gaia=[g]), catalog_pm_consistency=21.0, snr=40))
    assert ev.classification != "known_high_pm_star"


def test_identity_ranks_planets_after_their_host():
    from app.science.scoring import identity_matches
    planet = CatalogMatch(id="NAME Barnard's Star c", ra=1, dec=1, sep_arcsec=0.538, otype="Pl")
    star = CatalogMatch(id="NAME Barnard's Star", ra=1, dec=1, sep_arcsec=0.539, otype="BY*")
    ids = identity_matches(cm(simbad=[planet, star]))
    assert ids[0][1].id == "NAME Barnard's Star"
