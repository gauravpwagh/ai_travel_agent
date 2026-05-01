"""OpenRouteService travel-time wrapper with SQLite caching.

Every (origin, destination, profile) pair is cached so the 2 000 req/day
free-tier limit is never hit twice for the same leg. Falls back to a
haversine straight-line estimate when ORS is unavailable or the key is
absent (clearly labelled in the result so the UI can display it differently).

Public API
----------
    from src.routing.ors import annotate_itinerary_travel_times

    itinerary = annotate_itinerary_travel_times(itinerary, venue_lookup)
    # Each slot now has slot["travel_to_next"] = {
    #     "duration_s": 480, "distance_m": 650,
    #     "duration_min": 8, "source": "ors"
    # } or None for the last slot of the day.
"""
from __future__ import annotations

import math
import time

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from src.config import ORS_API_KEY, setup_logging
from src.db import get_travel_time, init_db, insert_travel_time

log = setup_logging()

ORS_BASE = "https://api.openrouteservice.org/v2/directions"
DEFAULT_PROFILE = "foot-walking"

# Assumed walking speed for haversine fallback (m/s)
WALK_SPEED_MS = 5_000 / 3_600  # 5 km/h

# Polite delay between ORS calls to stay within 40 req/min
_ORS_CALL_DELAY_S = 1.6


# ── Public API ────────────────────────────────────────────────────────────────

def annotate_itinerary_travel_times(
    itinerary: list[dict],
    venue_lookup: dict[str, dict],
    profile: str = DEFAULT_PROFILE,
) -> list[dict]:
    """Add travel_to_next to every slot in every day of the itinerary.

    The last slot of each day gets travel_to_next = None.
    Modifies the itinerary list in-place and also returns it.
    """
    init_db()  # ensure travel_times table exists
    for day in itinerary:
        slots = day.get("slots", [])
        _annotate_slots(slots, venue_lookup, profile)
    return itinerary


def day_total_transit_minutes(day: dict) -> int:
    """Sum the travel legs for one day. Returns 0 if no travel data.

    Uses ``or {}`` rather than a default argument so that an explicit
    ``travel_to_next: null`` (last slot / missing coords) is treated
    the same as an absent key — both coerce to an empty dict.
    """
    total_s = sum(
        (slot.get("travel_to_next") or {}).get("duration_s", 0) or 0
        for slot in day.get("slots", [])
    )
    return total_s // 60


# ── Per-day annotation ────────────────────────────────────────────────────────

def _annotate_slots(
    slots: list[dict],
    venue_lookup: dict[str, dict],
    profile: str,
) -> None:
    for i, slot in enumerate(slots):
        if i == len(slots) - 1:
            slot["travel_to_next"] = None
            continue

        origin_id = slot.get("osm_id", "")
        dest_id   = slots[i + 1].get("osm_id", "")
        origin    = venue_lookup.get(origin_id)
        dest      = venue_lookup.get(dest_id)

        if not origin or not dest:
            slot["travel_to_next"] = None
            continue

        result = _travel_time(origin, dest, origin_id, dest_id, profile)
        slot["travel_to_next"] = result


# ── Travel-time resolution (cache → ORS → haversine) ─────────────────────────

def _travel_time(
    origin: dict,
    dest: dict,
    origin_id: str,
    dest_id: str,
    profile: str,
) -> dict:
    # 1. SQLite cache hit
    cached = get_travel_time(origin_id, dest_id, profile)
    if cached:
        log.debug(f"Cache hit: {origin_id} → {dest_id}")
        return _enrich(cached)

    # 2. ORS API (only if key is set)
    if ORS_API_KEY:
        try:
            result = _call_ors(origin, dest, profile)
            insert_travel_time(
                origin_id, dest_id, profile,
                result["duration_s"], result["distance_m"], "ors",
            )
            log.info(
                f"ORS {origin_id[:12]}→{dest_id[:12]}: "
                f"{result['duration_s']//60} min / {result['distance_m']} m"
            )
            return _enrich(result)
        except Exception as exc:
            log.warning(f"ORS call failed ({exc}), falling back to haversine.")

    # 3. Haversine fallback
    result = _haversine_estimate(origin, dest)
    insert_travel_time(
        origin_id, dest_id, profile,
        result["duration_s"], result["distance_m"], "haversine",
    )
    return _enrich(result)


def _enrich(row: dict) -> dict:
    """Add human-readable duration_min to a travel-time dict."""
    return {
        **row,
        "duration_min": max(1, round(row["duration_s"] / 60)),
    }


# ── ORS HTTP call ─────────────────────────────────────────────────────────────

@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=15))
def _call_ors(origin: dict, dest: dict, profile: str) -> dict:
    time.sleep(_ORS_CALL_DELAY_S)          # polite rate limiting
    url = f"{ORS_BASE}/{profile}"
    payload = {
        "coordinates": [
            [origin["lon"], origin["lat"]],
            [dest["lon"],   dest["lat"]],
        ]
    }
    resp = requests.post(
        url,
        json=payload,
        headers={
            "Authorization": ORS_API_KEY,
            "Content-Type": "application/json",
        },
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    summary = data["routes"][0]["summary"]
    return {
        "duration_s": int(summary["duration"]),
        "distance_m": int(summary["distance"]),
        "source": "ors",
    }


# ── Haversine fallback ────────────────────────────────────────────────────────

def _haversine_estimate(origin: dict, dest: dict) -> dict:
    """Straight-line distance at walking speed. Clearly marked as estimate."""
    lat1, lon1 = math.radians(origin["lat"]), math.radians(origin["lon"])
    lat2, lon2 = math.radians(dest["lat"]),   math.radians(dest["lon"])

    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    distance_m = int(6_371_000 * 2 * math.asin(math.sqrt(a)))
    duration_s = int(distance_m / WALK_SPEED_MS)

    return {
        "duration_s": duration_s,
        "distance_m": distance_m,
        "source": "haversine",
    }
