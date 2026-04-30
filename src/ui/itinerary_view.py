"""Day-tab itinerary display: map (left) + venue card list (right).

Phase 2.4: each venue card now carries 👍 👎 🔄 feedback buttons.
"""
from __future__ import annotations

import streamlit as st

from src.routing.ors import day_total_transit_minutes
from src.ui.feedback import render_feedback_buttons
from src.ui.map_view import render_day_map
from src.validation.checks import ValidationIssue

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

def render_itinerary(
    itinerary:    list[dict],
    clusters:     list[list[dict]],
    issues:       list[ValidationIssue] | None = None,
    itinerary_id: int | None = None,
    venue_lookup: dict[str, dict] | None = None,
) -> None:
    """Render all days as Streamlit tabs, each with a map and venue cards."""
    _venue_lookup = venue_lookup or _build_venue_lookup(clusters)
    issues = issues or []

    tab_labels = [
        f"Day {d['day_number']} · {d.get('theme', '')}" for d in itinerary
    ]
    tabs = st.tabs(tab_labels)

    for tab, day in zip(tabs, itinerary):
        day_issues = [iss for iss in issues if iss.day_number == day["day_number"]]
        with tab:
            _render_day(day, _venue_lookup, day_issues, itinerary_id)


# ── Per-day layout ────────────────────────────────────────────────────────────

def _render_day(
    day:          dict,
    venue_lookup: dict[str, dict],
    issues:       list[ValidationIssue],
    itinerary_id: int | None,
) -> None:
    slots = day.get("slots", [])
    if not slots:
        st.warning("No venues for this day.")
        return

    _render_issue_banners(issues)

    total_min = day_total_transit_minutes(day)
    if total_min > 0:
        st.caption(f"🚶 ~{total_min} min total transit for this day")

    map_col, list_col = st.columns([3, 2], gap="large")

    with map_col:
        render_day_map(slots, venue_lookup)

    with list_col:
        _render_venue_cards(slots, day["day_number"], itinerary_id, venue_lookup)


# ── Validation issue banners ──────────────────────────────────────────────────

_CHECK_ICON: dict[str, str] = {
    "hallucination": "🔍",
    "opening_hours": "🕐",
    "transit":       "🚶",
    "rating":        "⭐",
}


def _render_issue_banners(issues: list[ValidationIssue]) -> None:
    if not issues:
        return
    with st.expander(f"🛡️ {len(issues)} validation notice(s)", expanded=False):
        for iss in issues:
            icon = _CHECK_ICON.get(iss.check, "ℹ️")
            if iss.auto_fixed:
                st.success(f"{icon} **Auto-fixed** ({iss.check}): {iss.message}")
            elif iss.severity == "error":
                st.error(f"{icon} **{iss.check}**: {iss.message}")
            else:
                st.warning(f"{icon} {iss.message}")


# ── Venue card list ───────────────────────────────────────────────────────────

def _render_venue_cards(
    slots:        list[dict],
    day_number:   int,
    itinerary_id: int | None,
    venue_lookup: dict[str, dict],
) -> None:
    for slot_idx, slot in enumerate(slots):
        _render_card(slot_idx + 1, slot, day_number, slot_idx, itinerary_id, venue_lookup)
        _render_leg_connector(slot)


def _render_card(
    n:            int,
    slot:         dict,
    day_number:   int,
    slot_idx:     int,
    itinerary_id: int | None,
    venue_lookup: dict[str, dict],
) -> None:
    name     = slot.get("venue_name", "Unknown")
    time     = slot.get("time", "")
    cat      = slot.get("category", "")
    desc     = slot.get("description", "")
    note     = slot.get("travel_note")
    duration = slot.get("duration_minutes")
    osm_id   = slot.get("osm_id", "")
    emoji    = _CATEGORY_EMOJI.get(cat, _DEFAULT_EMOJI)

    # Number badge + time
    badge_col, time_col = st.columns([1, 4])
    with badge_col:
        st.markdown(
            f'<div style="background:#4a90d9;color:#fff;border-radius:50%;'
            f'width:32px;height:32px;display:flex;align-items:center;'
            f'justify-content:center;font-weight:700;font-size:14px">{n}</div>',
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

    if desc:
        st.caption(desc)

    if note:
        st.markdown(
            f'<p style="color:#888;font-size:12px;margin-top:2px">🚶 {note}</p>',
            unsafe_allow_html=True,
        )

    # Feedback buttons
    if itinerary_id is not None and osm_id:
        render_feedback_buttons(
            day_number=day_number,
            slot_idx=slot_idx,
            osm_id=osm_id,
            itinerary_id=itinerary_id,
            venue_lookup=venue_lookup,
        )

    st.markdown(
        "<hr style='margin:10px 0;border:none;border-top:1px solid #eee'>",
        unsafe_allow_html=True,
    )


def _render_leg_connector(slot: dict) -> None:
    """Render a compact travel-time strip between two venue cards."""
    leg = slot.get("travel_to_next")
    if not leg:
        return

    mins     = leg.get("duration_min", 0)
    dist_m   = leg.get("distance_m", 0)
    source   = leg.get("source", "")
    dist_str = f"{dist_m / 1000:.1f} km" if dist_m >= 1000 else f"{dist_m} m"
    est_tag  = " *(est.)*" if source == "haversine" else ""

    st.markdown(
        f'<div style="display:flex;align-items:center;gap:8px;'
        f'margin:4px 0 4px 8px;color:#888;font-size:12px">'
        f"<span>🚶</span>"
        f"<span><b>{mins} min</b> · {dist_str}{est_tag}</span>"
        f"</div>",
        unsafe_allow_html=True,
    )


# ── Venue lookup ──────────────────────────────────────────────────────────────

def _build_venue_lookup(clusters: list[list[dict]]) -> dict[str, dict]:
    lookup: dict[str, dict] = {}
    for cluster in clusters:
        for venue in cluster:
            osm_id = venue.get("osm_id")
            if osm_id:
                lookup[osm_id] = venue
    return lookup
