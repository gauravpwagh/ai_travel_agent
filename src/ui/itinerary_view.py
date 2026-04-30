"""Day-tab itinerary display: map (left) + venue card list (right).

This is the value moment of the app — everything the user sees after
generation lives here.

Usage:
    from src.ui.itinerary_view import render_itinerary
    render_itinerary(itinerary, clusters)
"""
from __future__ import annotations

import streamlit as st

from src.ui.map_view import render_day_map

# Category → emoji badge shown on venue cards
_CATEGORY_EMOJI: dict[str, str] = {
    "food":       "🍽️",
    "cafe":       "☕",
    "beach":      "🏖️",
    "nature":     "🌿",
    "history":    "🏛️",
    "art":        "🎨",
    "museum":     "🎨",
    "nightlife":  "🎉",
    "shopping":   "🛍️",
    "attraction": "⭐",
    "viewpoint":  "🔭",
}
_DEFAULT_EMOJI = "📍"


# ── Public API ────────────────────────────────────────────────────────────────

def render_itinerary(itinerary: list[dict], clusters: list[list[dict]]) -> None:
    """Render all days as Streamlit tabs, each with a map and venue cards."""
    venue_lookup = _build_venue_lookup(clusters)

    tab_labels = [
        f"Day {d['day_number']} · {d.get('theme', '')}" for d in itinerary
    ]
    tabs = st.tabs(tab_labels)

    for tab, day in zip(tabs, itinerary):
        with tab:
            _render_day(day, venue_lookup)


# ── Per-day layout ────────────────────────────────────────────────────────────

def _render_day(day: dict, venue_lookup: dict[str, dict]) -> None:
    slots = day.get("slots", [])
    if not slots:
        st.warning("No venues for this day.")
        return

    map_col, list_col = st.columns([3, 2], gap="large")

    with map_col:
        render_day_map(slots, venue_lookup)

    with list_col:
        _render_venue_cards(slots)


# ── Venue card list ───────────────────────────────────────────────────────────

def _render_venue_cards(slots: list[dict]) -> None:
    for n, slot in enumerate(slots, 1):
        _render_card(n, slot)


def _render_card(n: int, slot: dict) -> None:
    name     = slot.get("venue_name", "Unknown")
    time     = slot.get("time", "")
    cat      = slot.get("category", "")
    desc     = slot.get("description", "")
    note     = slot.get("travel_note")
    duration = slot.get("duration_minutes")
    emoji    = _CATEGORY_EMOJI.get(cat, _DEFAULT_EMOJI)

    # Number badge + time on one line
    badge_col, time_col = st.columns([1, 4])
    with badge_col:
        st.markdown(
            f'<div style="'
            f"background:#4a90d9;color:#fff;border-radius:50%;"
            f"width:32px;height:32px;"
            f"display:flex;align-items:center;justify-content:center;"
            f'font-weight:700;font-size:14px">{n}</div>',
            unsafe_allow_html=True,
        )
    with time_col:
        dur_str = f" · {duration} min" if duration else ""
        st.markdown(f"**{time}**{dur_str}")

    # Venue name + category badge
    st.markdown(
        f"**{name}** &nbsp;"
        f'<span style="background:#f0f2f6;padding:2px 8px;border-radius:10px;'
        f'font-size:11px;color:#555">{emoji} {cat}</span>',
        unsafe_allow_html=True,
    )

    # Description
    if desc:
        st.caption(desc)

    # Travel note
    if note:
        st.markdown(
            f'<p style="color:#888;font-size:12px;margin-top:2px">🚶 {note}</p>',
            unsafe_allow_html=True,
        )

    st.markdown("<hr style='margin:10px 0;border:none;border-top:1px solid #eee'>",
                unsafe_allow_html=True)


# ── Venue lookup ──────────────────────────────────────────────────────────────

def _build_venue_lookup(clusters: list[list[dict]]) -> dict[str, dict]:
    """Build osm_id → venue dict from all clusters for quick coordinate lookup."""
    lookup: dict[str, dict] = {}
    for cluster in clusters:
        for venue in cluster:
            osm_id = venue.get("osm_id")
            if osm_id:
                lookup[osm_id] = venue
    return lookup
