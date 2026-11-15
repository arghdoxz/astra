"""Grounded explanation of an investigation's evidence.

Flow: build the compact evidence payload -> Gemini (if a key is configured) -> number grounding + forbidden-word
check -> one retry with feedback -> deterministic template. All 8 sections are always returned, in order.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from ..config import get_settings
from ..models import (SECTION_ORDER, SECTION_TITLES, ExplainRequest, Explanation, ExplanationSection,
                      Grounding, Investigation, Statement)
from .gemini import GeminiError, generate_json
from .grounding import check_sections, find_forbidden
from .prompts import (RESPONSE_SCHEMA, SYSTEM_INSTRUCTION, build_payload, build_user_prompt, retry_feedback)
from .templates import template_sections

log = logging.getLogger("astra.explain")

_KINDS = {"measured", "catalog", "interpretation", "hypothesis", "missing"}
MAX_STATEMENT_CHARS = 700
MAX_STATEMENTS_PER_SECTION = 6


def _normalize(data: Any, tmpl: list[ExplanationSection]) -> Optional[list[ExplanationSection]]:
    """Validate Gemini JSON into 8 ordered sections (missing/empty ones filled from the template)."""
    if not isinstance(data, dict) or not isinstance(data.get("sections"), list):
        return None
    got: dict[str, list[Statement]] = {}
    for sec in data["sections"]:
        if not isinstance(sec, dict) or sec.get("key") not in SECTION_ORDER:
            continue
        stmts = []
        for st in sec.get("statements") or []:
            if not isinstance(st, dict):
                continue
            text = st.get("text")
            kind = st.get("kind")
            if isinstance(text, str) and text.strip() and kind in _KINDS:
                stmts.append(Statement(kind=kind, text=text.strip()[:MAX_STATEMENT_CHARS]))
        if stmts and sec["key"] not in got:
            got[sec["key"]] = stmts[:MAX_STATEMENTS_PER_SECTION]
    if len(got) < len(SECTION_ORDER) // 2:
        return None
    by_tmpl = {t.key: t for t in tmpl}
    return [ExplanationSection(key=k, title=SECTION_TITLES[k], statements=got[k]) if k in got else by_tmpl[k]  # type: ignore[arg-type]
            for k in SECTION_ORDER]


def _all_text(sections: list[ExplanationSection]) -> str:
    return "\n".join(s.text for sec in sections for s in sec.statements)


def _template_explanation(payload: dict[str, Any], tmpl: list[ExplanationSection]) -> Explanation:
    g = check_sections(tmpl, payload)
    return Explanation(source="template", model=None, grounding=g, sections=tmpl)


async def explain(inv: Investigation, req: ExplainRequest, annotations: Optional[list[str]] = None) -> Explanation:
    """Raises LookupError if ``req`` names a candidate that does not exist. Never raises for AI failures."""
    payload = build_payload(inv, req)
    tmpl = template_sections(payload)
    if not get_settings().gemini_enabled:
        return _template_explanation(payload, tmpl)

    feedback: Optional[str] = None
    for _attempt in range(2):
        try:
            data, model = await generate_json(
                SYSTEM_INSTRUCTION, build_user_prompt(payload, req.question, annotations, feedback), RESPONSE_SCHEMA)
        except GeminiError as e:
            log.info("gemini unavailable, using template: %s", e)
            break
        except Exception as e:  # defensive: the fallback must always work
            log.info("gemini failed (%s), using template", type(e).__name__)
            break
        sections = _normalize(data, tmpl)
        if sections is None:
            feedback = "CORRECTION: your previous answer did not follow the required JSON structure. Regenerate the full JSON."
            continue
        g = check_sections(sections, payload)
        forbidden = find_forbidden(_all_text(sections))
        if g.passed and not forbidden:
            return Explanation(source="gemini", model=model, grounding=g, sections=sections)
        log.info("gemini output failed grounding (%d unmatched numbers, %d forbidden terms)",
                 len(g.unmatched_numbers), len(forbidden))
        feedback = retry_feedback(g.unmatched_numbers, forbidden)
    return _template_explanation(payload, tmpl)
