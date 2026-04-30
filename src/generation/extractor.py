"""Phase 2.3 — Free-text preference extraction.

Sends the user's free-form trip description to Groq and returns a
structured preference dict with the same shape as the form output.
Fields the text doesn't mention are returned as None / empty list.

Merge rule (CLAUDE.md): form values override extracted values on conflict.
The one exception is interests — form checkboxes and extracted interests
are unioned so neither source silently drops the other.

Public API
----------
    from src.generation.extractor import extract_preferences, merge_preferences

    extracted = extract_preferences("I want a 4-day beach holiday in Goa, budget travel")
    final     = merge_preferences(form_prefs, extracted)
"""
from __future__ import annotations

import json

from groq import Groq
from tenacity import retry, stop_after_attempt, wait_exponential

from src.config import GROQ_API_KEY, GROQ_MODEL, setup_logging
from src.generation.prompts import (
    PREFERENCE_EXTRACT_RETRY,
    PREFERENCE_EXTRACT_SCHEMA,
    PREFERENCE_EXTRACT_SYSTEM,
    PREFERENCE_EXTRACT_USER,
)

log = setup_logging()

# Canonical allowed values — must match forms.py constants
_VALID_INTERESTS   = {"food", "history", "nature", "nightlife", "shopping", "art", "beaches"}
_INTEREST_ORDER    = ["food", "history", "nature", "nightlife", "shopping", "art", "beaches"]
_VALID_BUDGET      = {"budget", "mid-range", "luxury"}
_VALID_PACE        = {"relaxed", "moderate", "packed"}
_DAYS_RANGE        = range(2, 8)   # 2-7 inclusive

_client: Groq | None = None


def _get_client() -> Groq:
    global _client
    if _client is None:
        if not GROQ_API_KEY:
            raise RuntimeError("GROQ_API_KEY is not set.")
        _client = Groq(api_key=GROQ_API_KEY)
    return _client


# ── Public API ────────────────────────────────────────────────────────────────

def extract_preferences(free_text: str) -> dict:
    """Extract structured preferences from free-form text via Groq.

    Returns a partial preference dict — fields not mentioned in the text
    are None (scalars) or [] (interests). Always safe to call merge_preferences
    on the result.

    Falls back to an empty dict on any error so the form values still work.
    """
    if not free_text.strip():
        return {}

    user_msg = PREFERENCE_EXTRACT_USER.format(
        free_text=free_text.strip(),
        schema=PREFERENCE_EXTRACT_SCHEMA,
    )
    messages = [
        {"role": "system", "content": PREFERENCE_EXTRACT_SYSTEM},
        {"role": "user",   "content": user_msg},
    ]

    try:
        raw = _call_groq(messages)
        return _parse_and_sanitize(raw)
    except Exception as exc:
        log.warning(f"extract_preferences: first attempt failed ({exc}), retrying…")

    # Single retry
    try:
        messages.append({"role": "assistant", "content": raw})   # type: ignore[possibly-undefined]
        messages.append({
            "role": "user",
            "content": PREFERENCE_EXTRACT_RETRY.format(schema=PREFERENCE_EXTRACT_SCHEMA),
        })
        raw2 = _call_groq(messages)
        return _parse_and_sanitize(raw2)
    except Exception as exc:
        log.error(f"extract_preferences: retry also failed ({exc}). Returning empty dict.")
        return {}


def merge_preferences(form_prefs: dict, extracted: dict) -> dict:
    """Merge extracted preferences into form preferences.

    Merge rules
    -----------
    interests : UNION — both the form checkboxes and extracted interests
                are preserved. Preserves canonical ordering.
    all other fields : form wins. Extracted values are only used to fill
                fields where the form hasn't provided a value (None / 0).

    This means a user who explicitly set Budget=luxury in the form won't
    have it silently downgraded by "I'm on a budget" in their description.
    """
    if not extracted:
        return form_prefs

    merged = dict(form_prefs)

    # Interests: union, preserving canonical order
    form_interests = set(form_prefs.get("interests") or [])
    ext_interests  = set(extracted.get("interests") or []) & _VALID_INTERESTS
    all_interests  = form_interests | ext_interests
    merged["interests"] = [i for i in _INTEREST_ORDER if i in all_interests]

    log.info(
        f"Preference merge — form interests: {sorted(form_interests)}, "
        f"extracted interests: {sorted(ext_interests)}, "
        f"merged: {merged['interests']}"
    )

    if ext_interests - form_interests:
        merged["_extracted_interests"] = sorted(ext_interests - form_interests)

    return merged


def extraction_summary(extracted: dict) -> str | None:
    """Return a short human-readable summary of what was extracted, for the UI."""
    if not extracted:
        return None
    parts: list[str] = []
    if extracted.get("interests"):
        parts.append(f"interests: {', '.join(extracted['interests'])}")
    if extracted.get("budget_tier"):
        parts.append(f"budget: {extracted['budget_tier']}")
    if extracted.get("pace"):
        parts.append(f"pace: {extracted['pace']}")
    if extracted.get("days"):
        parts.append(f"{extracted['days']} days")
    if extracted.get("party_size"):
        parts.append(f"{extracted['party_size']} travellers")
    return "; ".join(parts) if parts else None


# ── Groq call ─────────────────────────────────────────────────────────────────

@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=15))
def _call_groq(messages: list[dict]) -> str:
    client = _get_client()
    resp = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=messages,
        response_format={"type": "json_object"},
        temperature=0.0,   # deterministic — extraction, not generation
        max_tokens=300,
    )
    return resp.choices[0].message.content or ""


# ── Parsing + sanitisation ────────────────────────────────────────────────────

def _parse_and_sanitize(raw: str) -> dict:
    """Parse JSON response and scrub any values outside allowed enums."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON decode error: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError("Expected a JSON object at the top level.")

    # interests — filter to valid set only
    raw_interests = data.get("interests") or []
    data["interests"] = [i for i in raw_interests if i in _VALID_INTERESTS]

    # budget_tier — null if not in allowed set
    if data.get("budget_tier") not in _VALID_BUDGET:
        data["budget_tier"] = None

    # pace — null if not in allowed set
    if data.get("pace") not in _VALID_PACE:
        data["pace"] = None

    # days — null if out of range
    days = data.get("days")
    if days is not None:
        try:
            days = int(days)
            data["days"] = days if days in _DAYS_RANGE else None
        except (TypeError, ValueError):
            data["days"] = None

    # party_size — null if not a positive int
    ps = data.get("party_size")
    if ps is not None:
        try:
            ps = int(ps)
            data["party_size"] = ps if ps > 0 else None
        except (TypeError, ValueError):
            data["party_size"] = None

    log.debug(f"Extracted preferences: {data}")
    return data
