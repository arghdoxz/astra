"""Number-grounding check for AI explanations.

Every number in the generated text must be traceable to the evidence JSON that was sent to the model:
* integers must equal an evidence number exactly (or equal it rounded to an integer);
* decimals must be within 1 % relative of an evidence number, or equal it rounded to the displayed precision
  (3982.0 vs 3982, 0.547 vs 0.55);
* signs are ignored (a direction word carries the sign), a percentage may be 100 x a fraction in the evidence;
* digits glued to letters (D3, v0, c2, W2, chi2_red) are identifiers, not quantities, and are ignored.
"""
from __future__ import annotations

import re
from typing import Any, Iterable

from ..models import Grounding

NUM_RE = re.compile(r"(?<![A-Za-z0-9_.])(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:[eE][+-]?\d+)?")
FORBIDDEN_RE = re.compile(r"\b(discover(?:y|ies|ed|s|ing)?|new planets?|planet\s*x)\b", re.IGNORECASE)


def extract_numbers(text: str) -> list[str]:
    """Number tokens in ``text`` (unicode minus / thousands separators tolerated)."""
    return NUM_RE.findall(text.replace("−", "-"))


def find_forbidden(text: str) -> list[str]:
    return [m.group(0) for m in FORBIDDEN_RE.finditer(text)]


def _clean(tok: str) -> str:
    return tok.replace(",", "")


def collect_evidence_numbers(obj: Any) -> tuple[set[float], set[str]]:
    """All numeric leaves (as abs floats) and all number tokens found inside string leaves."""
    nums: set[float] = set()
    toks: set[str] = set()

    def walk(o: Any) -> None:
        if isinstance(o, bool) or o is None:
            return
        if isinstance(o, (int, float)):
            if o == o and abs(o) != float("inf"):
                nums.add(abs(float(o)))
        elif isinstance(o, str):
            for t in extract_numbers(o):
                c = _clean(t)
                toks.add(c)
                try:
                    nums.add(abs(float(c)))
                except ValueError:
                    pass
        elif isinstance(o, dict):
            for v in o.values():
                walk(v)
        elif isinstance(o, (list, tuple, set)):
            for v in o:
                walk(v)

    walk(obj)
    return nums, toks


def _decimals(clean: str) -> int | None:
    if "e" in clean.lower():
        return None
    return len(clean.split(".")[1]) if "." in clean else 0


def _token_ok(tok: str, nums: Iterable[float], toks: set[str]) -> bool:
    c = _clean(tok)
    if c in toks:
        return True
    try:
        n = float(c)
    except ValueError:
        return True
    dec = _decimals(c)
    for e in nums:
        for cand in (e, e * 100.0):
            if dec == 0:
                if abs(n - cand) < 1e-9 or abs(round(cand) - n) < 1e-9:
                    return True
            elif dec is None:
                if abs(n - cand) <= 0.01 * abs(cand) + 1e-12:
                    return True
            else:
                if abs(n - cand) <= 0.01 * abs(cand) + 1e-12 or abs(round(cand, dec) - n) < 1e-9:
                    return True
    return False


def check_text(text: str, evidence: Any) -> Grounding:
    nums, toks = collect_evidence_numbers(evidence)
    return check_with(text, nums, toks)


def check_with(text: str, nums: set[float], toks: set[str]) -> Grounding:
    bad: list[str] = []
    for tok in extract_numbers(text):
        if not _token_ok(tok, nums, toks) and tok not in bad:
            bad.append(tok)
    return Grounding(passed=not bad, unmatched_numbers=bad)


def check_sections(sections: Iterable[Any], evidence: Any) -> Grounding:
    """Ground every statement of ExplanationSection objects (or dicts with 'statements')."""
    nums, toks = collect_evidence_numbers(evidence)
    bad: list[str] = []
    for sec in sections:
        stmts = sec["statements"] if isinstance(sec, dict) else sec.statements
        for st in stmts:
            text = st["text"] if isinstance(st, dict) else st.text
            for tok in check_with(text, nums, toks).unmatched_numbers:
                if tok not in bad:
                    bad.append(tok)
    return Grounding(passed=not bad, unmatched_numbers=bad)
