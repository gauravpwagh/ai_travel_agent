"""Phase 1.5 — LLM itinerary assembly via Groq.

One Groq call per day cluster produces a structured JSON day-plan.
JSON is validated on parse; a single retry with a stricter prompt is
attempted on failure before raising.

Usage:
    from src.generation.itinerary import build_itinerary

    itinerary = build_itinerary(clusters, preferences)
    # itinerary = [{"day_number": 1, "theme": "...", "slots": [...]}, ...]
"""
from __future__ import annotations

import json
import time

from groq import Groq
from tenacity import retry, stop_after_attempt, wait_exponential

from src.config import GROQ_API_KEY, GROQ_MODEL, setup_logging
from src.generation.prompts import (
    DAY_ITINERARY_RETRY,
    DAY_ITINERARY_SCHEMA,
    DAY_ITINERARY_SYSTEM,
    DAY_ITINERARY_USER,
)

log = setup_logging()

USER_ID = "demo_user"

_client: Groq | None = None


def _get_client() -> Groq:
    global _client
    if _client is None:
        if not GROQ_API_KEY:
            raise RuntimeError("GROQ_API_KEY is not set. Add it to your .env file.")
        _client = Groq(api_key=GROQ_API_KEY)
    return _client


# ── Public API ────────────────────────────────────────────────────────────────

def build_itinerary(
    clusters: list[list[dict]],
    preferences: dict,
) -> list[dict]:
    """Assemble a full multi-day itinerary from day clusters.

    Makes one Groq call per day. Returns a list of day dicts ordered Day 1…N.
    """
    days: list[dict] = []
    for i, cluster in enumerate(clusters):
        day_num = i + 1
        log.info(f"Assembling Day {day_num} ({len(cluster)} candidate venues)…")
        day = _assemble_day(day_num, cluster, preferences)
        days.append(day)
        # Groq free tier: stay well under rate limits between calls
        if i < len(clusters) - 1:
            time.sleep(0.5)

    return days


# ── Per-day assembly ──────────────────────────────────────────────────────────

def _assemble_day(day_num: int, cluster: list[dict], preferences: dict) -> dict:
    """Call Groq for one day's cluster. Retries once on JSON parse failure."""
    venue_list = _build_venue_context(cluster)
    user_msg = DAY_ITINERARY_USER.format(
        day_number=day_num,
        destination=preferences["destination"],
        date_label=f"Day {day_num}",
        budget_tier=preferences["budget_tier"],
        pace_label=preferences["pace"],
        interests=", ".join(preferences.get("interests", [])),
        venue_list=venue_list,
        schema=DAY_ITINERARY_SCHEMA,
    )

    messages = [
        {"role": "system", "content": DAY_ITINERARY_SYSTEM},
        {"role": "user", "content": user_msg},
    ]

    raw = _call_groq(messages)

    try:
        day_dict = _parse_and_validate(raw, day_num, cluster)
        return day_dict
    except ValueError as exc:
        log.warning(f"Day {day_num} parse failed ({exc}), retrying with stricter prompt…")

    # Single retry: append the bad response and a correction instruction
    messages.append({"role": "assistant", "content": raw})
    messages.append({
        "role": "user",
        "content": DAY_ITINERARY_RETRY.format(schema=DAY_ITINERARY_SCHEMA),
    })
    raw2 = _call_groq(messages)
    try:
        return _parse_and_validate(raw2, day_num, cluster)
    except ValueError as exc:
        log.error(f"Day {day_num} failed after retry: {exc}")
        return _fallback_day(day_num, cluster)


# ── Groq call ─────────────────────────────────────────────────────────────────

@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=20))
def _call_groq(messages: list[dict]) -> str:
    client = _get_client()
    response = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=messages,
        response_format={"type": "json_object"},
        temperature=0.3,
        max_tokens=1500,
    )
    content = response.choices[0].message.content or ""
    log.debug(f"Groq response ({len(content)} chars)")
    return content


# ── Venue context builder ─────────────────────────────────────────────────────

def _build_venue_context(cluster: list[dict]) -> str:
    """Format cluster venues into a numbered list for the prompt."""
    lines: list[str] = []
    for i, v in enumerate(cluster, 1):
        cats = ", ".join(v.get("categories") or [])
        hours = v.get("opening_hours") or "hours unknown"
        tags: dict = v.get("tags") or {}

        parts = [f"{i}. {v['name']} [{cats}]"]
        parts.append(f"osm_id: {v['osm_id']}")
        parts.append(f"hours: {hours}")

        if "cuisine" in tags:
            parts.append(f"cuisine: {tags['cuisine'].replace(';', ', ')}")
        extras = [
            flag for flag in ("outdoor_seating", "vegetarian", "vegan", "rooftop")
            if tags.get(flag) in ("yes", "only")
        ]
        if extras:
            parts.append(", ".join(extras))

        lines.append(" | ".join(parts))
    return "\n".join(lines)


# ── JSON validation ───────────────────────────────────────────────────────────

def _parse_and_validate(raw: str, day_num: int, cluster: list[dict]) -> dict:
    """Parse LLM output and check it matches the expected schema.

    Raises ValueError with a descriptive message on any problem so the caller
    can decide whether to retry.
    """
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON decode error: {exc}") from exc

    if "slots" not in data or not isinstance(data["slots"], list):
        raise ValueError("Missing or non-list 'slots' key")

    if not data["slots"]:
        raise ValueError("'slots' is empty")

    # Build a lookup of valid osm_ids in this cluster for grounding check
    valid_osm_ids = {v["osm_id"] for v in cluster}

    for slot in data["slots"]:
        for required in ("time", "venue_name", "osm_id", "description"):
            if required not in slot:
                raise ValueError(f"Slot missing required key '{required}'")

        osm_id = slot.get("osm_id", "")
        if osm_id not in valid_osm_ids:
            # Hallucinated venue — remove the slot rather than failing entirely
            log.warning(
                f"Day {day_num}: slot '{slot.get('venue_name')}' has unknown "
                f"osm_id '{osm_id}' — dropping slot."
            )

    # Filter out hallucinated slots in-place
    data["slots"] = [s for s in data["slots"] if s.get("osm_id") in valid_osm_ids]

    if not data["slots"]:
        raise ValueError("All slots were hallucinated — no valid venues remain")

    data.setdefault("day_number", day_num)
    data.setdefault("theme", f"Day {day_num} in {cluster[0].get('destination', '')}")
    return data


# ── Fallback ──────────────────────────────────────────────────────────────────

def _fallback_day(day_num: int, cluster: list[dict]) -> dict:
    """Minimal valid day dict built from raw cluster data, no LLM."""
    log.warning(f"Using fallback (no LLM) for Day {day_num}.")
    slots = []
    base_hour = 9
    for v in cluster[:5]:
        slots.append({
            "time": f"{base_hour:02d}:00",
            "venue_name": v["name"],
            "osm_id": v["osm_id"],
            "category": (v.get("categories") or ["unknown"])[0],
            "duration_minutes": 60,
            "description": v.get("description") or v["name"],
            "travel_note": None,
        })
        base_hour += 2
    return {
        "day_number": day_num,
        "theme": f"Day {day_num}",
        "slots": slots,
    }
