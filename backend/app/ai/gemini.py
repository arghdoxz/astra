"""Minimal Gemini REST client (generateContent with JSON-schema output).

The API key is read from settings and sent ONLY in the ``x-goog-api-key`` header; it is never logged, put in a URL,
or included in an exception message.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

import httpx

from ..config import get_settings
from ..services import http

log = logging.getLogger("astra.gemini")

BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
TIMEOUT_S = 30.0
FALLBACK_STATUSES = frozenset({404, 429})


class GeminiError(RuntimeError):
    """Gemini call failed (message never contains the API key)."""


def _fallbackable(status: Optional[int]) -> bool:
    return status is None or status in FALLBACK_STATUSES or status >= 500


async def _call(model: str, body: dict[str, Any], key: str) -> tuple[Optional[int], dict[str, Any]]:
    """One request. Returns (status_code, json). status None = network failure/timeout."""
    try:
        resp = await http.fetch("POST", BASE_URL.format(model=model), json=body,
                                headers={"x-goog-api-key": key, "Content-Type": "application/json"},
                                timeout=TIMEOUT_S, retries=1, raise_for_status=False)
    except (httpx.HTTPError, OSError) as e:
        log.info("gemini %s network failure: %s", model, type(e).__name__)
        return None, {}
    try:
        data = resp.json()
    except ValueError:
        data = {}
    return resp.status_code, data if isinstance(data, dict) else {}


def _extract_text(data: dict[str, Any]) -> str:
    cands = data.get("candidates") or []
    if not cands:
        fb = (data.get("promptFeedback") or {}).get("blockReason")
        raise GeminiError(f"no candidates returned{f' (blocked: {fb})' if fb else ''}")
    c = cands[0]
    parts = (c.get("content") or {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts if isinstance(p, dict) and not p.get("thought"))
    if not text.strip():
        raise GeminiError(f"empty response (finishReason={c.get('finishReason')})")
    return text


async def generate_json(system: str, user: str, schema: dict[str, Any], *, model: Optional[str] = None,
                        temperature: float = 0.2) -> tuple[dict[str, Any], str]:
    """Returns (parsed JSON object, model actually used). Raises GeminiError."""
    s = get_settings()
    if not s.gemini_api_key:
        raise GeminiError("Gemini is not configured")
    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {"responseMimeType": "application/json", "responseSchema": schema,
                             "temperature": temperature},
    }
    models = [model or s.gemini_model]
    if s.gemini_fallback_model and s.gemini_fallback_model not in models:
        models.append(s.gemini_fallback_model)
    last = "unknown error"
    for i, m in enumerate(models):
        status, data = await _call(m, body, s.gemini_api_key)
        if status == 200:
            try:
                return json.loads(_extract_text(data)), m
            except (GeminiError, ValueError) as e:
                last = f"{m}: unusable response ({type(e).__name__})"
                continue            # try the fallback model once as well
        last = f"{m}: HTTP {status}" if status else f"{m}: network failure"
        if not _fallbackable(status) or i == len(models) - 1:
            break
    raise GeminiError(last)
