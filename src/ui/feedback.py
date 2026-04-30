"""Phase 2.4 — Feedback buttons: thumbs up/down and venue swap.

Feedback events are logged to the SQLite `feedback` table on every click.
The itinerary is cached in st.session_state so the expensive generation
pipeline is never re-run just because a user tapped 👍.

Swap strategy (no extra LLM call — fast path):
  1. Find candidate venues in the day's cluster that are not already in
     any of the day's current slots.
  2. Pick the highest similarity_score alternative.
  3. Replace the slot in-place, keeping the original time slot and duration.
  4. Re-annotate travel times for just that day.
  5. Update st.session_state["itinerary"] and call st.rerun().
"""
from __future__ import annotations

import streamlit as st

from src.db import get_venue_id, insert_feedback
from src.routing.ors import annotate_itinerary_travel_times

# session_state key that holds all generated data between reruns
_STATE_KEY = "itinerary_state"


# ── Session-state helpers ─────────────────────────────────────────────────────

def save_itinerary_state(
    itinerary:    list[dict],
    clusters:     list[list[dict]],
    issues:       list,
    itinerary_id: int,
    venue_lookup: dict[str, dict],
    preferences:  dict,
) -> None:
    """Persist all generated data so feedback reruns don't re-run the pipeline."""
    st.session_state[_STATE_KEY] = {
        "itinerary":    itinerary,
        "clusters":     clusters,
        "issues":       issues,
        "itinerary_id": itinerary_id,
        "venue_lookup": venue_lookup,
        "preferences":  preferences,
        "ratings":      {},       # osm_id → 'up' | 'down'
    }


def load_itinerary_state() -> dict | None:
    """Return the cached state dict, or None if not yet generated."""
    return st.session_state.get(_STATE_KEY)


def clear_itinerary_state() -> None:
    """Called on new form submission to force a fresh pipeline run."""
    st.session_state.pop(_STATE_KEY, None)


# ── Feedback button component ─────────────────────────────────────────────────

def render_feedback_buttons(
    day_number:   int,
    slot_idx:     int,
    osm_id:       str,
    itinerary_id: int,
    venue_lookup: dict[str, dict],
) -> None:
    """Render 👍 👎 🔄 buttons for one venue slot."""
    state   = st.session_state.get(_STATE_KEY, {})
    ratings = state.get("ratings", {})
    current = ratings.get(osm_id)

    up_label   = "👍 Liked"   if current == "up"   else "👍"
    down_label = "👎 Disliked" if current == "down" else "👎"

    btn_up, btn_down, btn_swap = st.columns([1, 1, 1])

    venue_id = venue_lookup.get(osm_id, {}).get("id") or get_venue_id(osm_id)

    with btn_up:
        if st.button(
            up_label,
            key=f"up_{itinerary_id}_{day_number}_{slot_idx}",
            use_container_width=True,
            disabled=(current == "up"),
        ):
            insert_feedback(itinerary_id, venue_id, day_number, "thumbs_up")
            state.setdefault("ratings", {})[osm_id] = "up"
            st.session_state[_STATE_KEY] = state

    with btn_down:
        if st.button(
            down_label,
            key=f"down_{itinerary_id}_{day_number}_{slot_idx}",
            use_container_width=True,
            disabled=(current == "down"),
        ):
            insert_feedback(itinerary_id, venue_id, day_number, "thumbs_down")
            state.setdefault("ratings", {})[osm_id] = "down"
            st.session_state[_STATE_KEY] = state

    with btn_swap:
        if st.button(
            "🔄 Swap",
            key=f"swap_{itinerary_id}_{day_number}_{slot_idx}",
            use_container_width=True,
        ):
            insert_feedback(itinerary_id, venue_id, day_number, "swap")
            with st.spinner(f"Finding a replacement venue…"):
                _do_swap(day_number, slot_idx, osm_id)
            st.rerun()


# ── Swap logic ────────────────────────────────────────────────────────────────

def _do_swap(day_number: int, slot_idx: int, old_osm_id: str) -> None:
    """Replace one slot with the best unused alternative from the day's cluster."""
    state        = st.session_state[_STATE_KEY]
    itinerary    = state["itinerary"]
    clusters     = state["clusters"]
    venue_lookup = state["venue_lookup"]

    day_idx  = day_number - 1
    day      = itinerary[day_idx]
    cluster  = clusters[day_idx] if day_idx < len(clusters) else []
    slots    = day.get("slots", [])

    # osm_ids already in the day (excluding the slot being swapped)
    occupied = {
        s["osm_id"] for i, s in enumerate(slots)
        if i != slot_idx and s.get("osm_id")
    }

    # Candidates: in the cluster, not already in the day, not the same venue
    candidates = [
        v for v in cluster
        if v["osm_id"] != old_osm_id and v["osm_id"] not in occupied
    ]

    if not candidates:
        st.warning("No alternative venues available for this slot.")
        return

    # Pick highest similarity_score
    best = max(candidates, key=lambda v: v.get("similarity_score", 0.0))

    # Build replacement slot, keeping the original time and duration
    old_slot = slots[slot_idx]
    new_slot = {
        "time":             old_slot.get("time", ""),
        "venue_name":       best["name"],
        "osm_id":           best["osm_id"],
        "category":         (best.get("categories") or ["unknown"])[0],
        "duration_minutes": old_slot.get("duration_minutes", 60),
        "description":      best.get("description") or best["name"],
        "travel_note":      None,
        "travel_to_next":   None,
    }

    slots[slot_idx] = new_slot

    # Re-annotate travel times for this day only
    annotate_itinerary_travel_times([day], venue_lookup)

    # Persist
    state["itinerary"] = itinerary
    st.session_state[_STATE_KEY] = state
