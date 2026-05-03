"""Day-tab itinerary display: map (left) + venue card list (right).

Phase 2.4: each venue card now carries 👍 👎 🔄 feedback buttons.
UI refresh: modern card layout, category pills, timeline connector.
"""
from __future__ import annotations

import streamlit as st

from src.routing.ors import day_total_transit_minutes
from src.ui.feedback import render_feedback_buttons
from src.ui.map_view import render_day_map
from src.validation.checks import ValidationIssue

# Category → Bootstrap Icon class + accent colour
_CATEGORY_META: dict[str, dict] = {
    "food":       {"icon": "bi-cup-hot",          "colour": "#E05C2A"},
    "cafe":       {"icon": "bi-cup-hot",           "colour": "#D97706"},
    "beach":      {"icon": "bi-umbrella",          "colour": "#0284C7"},
    "nature":     {"icon": "bi-tree",              "colour": "#16A34A"},
    "history":    {"icon": "bi-bank",              "colour": "#92400E"},
    "art":        {"icon": "bi-palette",           "colour": "#7C3AED"},
    "museum":     {"icon": "bi-palette",           "colour": "#7C3AED"},
    "nightlife":  {"icon": "bi-moon-stars",        "colour": "#4338CA"},
    "shopping":   {"icon": "bi-bag",               "colour": "#0E7490"},
    "attraction": {"icon": "bi-star-fill",         "colour": "#0F766E"},
    "viewpoint":  {"icon": "bi-binoculars",        "colour": "#0F766E"},
}
_DEFAULT_META = {"icon": "bi-pin-map-fill", "colour": "#475569"}

_CHECK_ICON: dict[str, str] = {
    "hallucination": "🔍",
    "opening_hours": "🕐",
    "transit":       "🚶",
    "rating":        "⭐",
}


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
        f"Day {d['day_number']}  {d.get('theme', '')}" for d in itinerary
    ]
    tabs = st.tabs(tab_labels)

    for tab, day in zip(tabs, itinerary):
        day_issues = [i for i in issues if i.day_number == day["day_number"]]
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

    # Day summary bar
    total_min = day_total_transit_minutes(day)
    n_venues  = len(slots)
    summary_parts = [f"<strong>{n_venues} stops</strong>"]
    if total_min > 0:
        summary_parts.append(f'<i class="bi bi-person-walking"></i> ~{total_min} min transit')

    st.markdown(
        f"""<div style="display:flex;align-items:center;gap:12px;
                padding:.55rem 1rem;background:#F0F9FF;border-radius:10px;
                border:1px solid #BAE6FD;margin-bottom:.75rem;font-size:.9rem;color:#0284C7">
            {"&nbsp;·&nbsp;".join(summary_parts)}
        </div>""",
        unsafe_allow_html=True,
    )

    _render_issue_banners(issues)

    # ── Map (3) | Scrollable venue cards (2) — same height ───────────────────
    MAP_H = 500
    map_col, cards_col = st.columns([3, 2], gap="medium")

    with map_col:
        render_day_map(
            slots=slots,
            venue_lookup=venue_lookup,
            day_number=day["day_number"],
            itinerary_id=itinerary_id or 0,
            height=MAP_H,
        )

    with cards_col:
        with st.container(height=MAP_H, border=False):
            _render_venue_cards(slots, day["day_number"], itinerary_id, venue_lookup)


# ── Validation issue banners ──────────────────────────────────────────────────

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


# ── Venue cards ───────────────────────────────────────────────────────────────

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
    duration = slot.get("duration_minutes")
    osm_id   = slot.get("osm_id", "")
    meta     = _CATEGORY_META.get(cat, _DEFAULT_META)
    colour   = meta["colour"]
    icon_cls = meta["icon"]

    with st.container(border=True):
        # Top row: number badge + venue name + time + category pill
        hdr_left, hdr_right = st.columns([5, 2])

        with hdr_left:
            dur_str = f"<span style='color:#94A3B8;font-size:.8rem'> · {duration} min</span>" if duration else ""
            st.markdown(
                f"""<div style="display:flex;align-items:center;gap:10px">
                    <div style="background:{colour};color:#fff;border-radius:50%;
                        min-width:28px;width:28px;height:28px;display:flex;
                        align-items:center;justify-content:center;
                        font-weight:700;font-size:12px;
                        box-shadow:0 2px 6px {colour}55">{n}</div>
                    <div>
                        <span style="font-weight:700;font-size:.97rem;color:#0F172A">{name}</span>
                        {dur_str}
                    </div>
                </div>""",
                unsafe_allow_html=True,
            )

        with hdr_right:
            st.markdown(
                f"""<div style="display:flex;justify-content:flex-end;align-items:center;gap:6px;padding-top:2px">
                    <span style="background:#F0F9FF;border:1px solid #BAE6FD;
                        padding:2px 10px;border-radius:20px;
                        font-size:.75rem;font-weight:600;color:{colour};white-space:nowrap">
                        <i class="bi {icon_cls}"></i> {cat}
                    </span>
                    <span style="font-size:.82rem;font-weight:600;color:#0EA5E9;white-space:nowrap">
                        <i class="bi bi-clock"></i> {time}
                    </span>
                </div>""",
                unsafe_allow_html=True,
            )

        # Description
        if desc:
            st.markdown(
                f'<p style="margin:.4rem 0 .1rem;font-size:.85rem;color:#475569;line-height:1.5">{desc}</p>',
                unsafe_allow_html=True,
            )

        # Feedback buttons
        if itinerary_id is not None and osm_id:
            st.markdown('<div class="feedback-row">', unsafe_allow_html=True)
            render_feedback_buttons(
                day_number=day_number,
                slot_idx=slot_idx,
                osm_id=osm_id,
                itinerary_id=itinerary_id,
                venue_lookup=venue_lookup,
            )
            st.markdown('</div>', unsafe_allow_html=True)


def _render_leg_connector(slot: dict) -> None:
    """Compact travel-time strip between consecutive venue cards."""
    leg = slot.get("travel_to_next")
    if not leg:
        return
    mins     = leg.get("duration_min", 0)
    dist_m   = leg.get("distance_m", 0)
    source   = leg.get("source", "")
    dist_str = f"{dist_m / 1000:.1f} km" if dist_m >= 1000 else f"{dist_m} m"
    est_tag  = " <i style='color:#CBD5E1'>(est.)</i>" if source == "haversine" else ""

    st.markdown(
        f"""<div class="leg-connector">
            <span style="color:#BAE6FD">┆</span>
            <span><i class="bi bi-person-walking"></i> <b>{mins} min</b> · {dist_str}{est_tag}</span>
        </div>""",
        unsafe_allow_html=True,
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_venue_lookup(clusters: list[list[dict]]) -> dict[str, dict]:
    lookup: dict[str, dict] = {}
    for cluster in clusters:
        for venue in cluster:
            osm_id = venue.get("osm_id")
            if osm_id:
                lookup[osm_id] = venue
    return lookup
