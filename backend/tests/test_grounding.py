from app.ai.grounding import (check_sections, check_text, collect_evidence_numbers, extract_numbers,
                              find_forbidden)
from app.models import ExplanationSection, Statement

EVIDENCE = {
    "pm_ra": -801.6, "pm_dec": 10362.4, "mu": 3982.0, "frac": 0.547, "snr": 12.34,
    "n": 3, "detectors": [1, 2, 3], "expl": "Offset is 4.21 sigma over 2 visits (2025-08)", "big": 1234567.0,
}


def ok(text):
    return check_text(text, EVIDENCE).passed


def test_extract_numbers_handles_formats():
    assert extract_numbers("a 3,982.5 and -801.6 and 1.5e-3 and −2.5") == ["3,982.5", "801.6", "1.5e-3", "2.5"]
    toks = extract_numbers("D3 at 12.3 sigma, v0, c2, W2 flux 7 and 1,234")
    assert toks == ["12.3", "7", "1,234"]            # identifiers glued to letters are ignored


def test_exact_and_rounded_match():
    assert ok("The proper motion is 3982 mas/yr.")           # 3982.0 shown as an integer
    assert ok("It moved 3,982.0 mas/yr.")
    assert ok("The value is 0.55 of the total.")             # 0.547 rounded to 2 dp
    assert ok("SNR of 12.3 sigma.")                           # 12.34 rounded to 1 dp
    assert ok("SNR of 12.34 sigma.")
    assert ok("Moving west at 801.6 mas/yr.")                 # sign ignored
    assert ok("The offset is 4.21 sigma.")                    # number inside a string leaf
    assert ok("Seen in 3 detectors.")


def test_tolerance_is_one_percent_for_decimals():
    assert ok("About 10400.0 mas/yr.")                        # 0.4 % away: allowed by the 1 % rule
    assert ok("pm_dec of 10360.0")                            # within 1 % of 10362.4
    assert not ok("pm_dec of 10700.5")                        # > 1 % away


def test_unmatched_numbers_are_reported():
    g = check_text("The star moves 88.8 mas/yr in 17 detectors, SNR 12.34.", EVIDENCE)
    assert not g.passed
    assert g.unmatched_numbers == ["88.8", "17"]


def test_integers_must_match_exactly():
    assert not ok("It has 5 detectors.")                      # 5 is not in the evidence
    assert ok("Detectors 1, 2 and 3.")


def test_percentages_of_fractions():
    assert ok("About 54.7% of the points.")


def test_nothing_numeric_passes():
    assert ok("No numbers here, just words and D4 or v2.")


def test_forbidden_words():
    assert find_forbidden("This is a discovery of a new planet near Planet X.") == ["discovery", "new planet", "Planet X"]
    assert find_forbidden("Unexplained - needs human review") == []


def test_check_sections_over_objects_and_dicts():
    secs = [ExplanationSection(key="summary", title="Summary", statements=[Statement(kind="measured", text="SNR 12.34 sigma")]),
            {"key": "movement", "statements": [{"kind": "measured", "text": "moved 55.5 mas/yr"}]}]
    g = check_sections(secs, EVIDENCE)
    assert not g.passed and g.unmatched_numbers == ["55.5"]


def test_collect_evidence_numbers():
    nums, toks = collect_evidence_numbers(EVIDENCE)
    assert 801.6 in nums and 3982.0 in nums and "4.21" in toks and "2025" in toks
