"""Folium map rendering for one day's itinerary slots.

Bug fixes (Phase 2.8+):
- Each day's map gets a unique ``key`` so Streamlit does not reuse the
  same widget instance across tabs, which was causing zoom-reset on tab
  switch.
- ``fit_bounds`` is always called (even for a single venue) so the
  map shows an appropriate zoom level rather than the hard-coded
  zoom_start default.
"""
from __future__ import annotations

import folium
from streamlit_folium import st_folium

# ── Category → marker colour ──────────────────────────────────────────────────
_CATEGORY_COLOUR: dict[str, str] = {
    "food":        "#E05C2A",
    "cafe":        "#D97706",
    "beach":       "#0284C7",
    "nature":      "#16A34A",
    "history":     "#92400E",
    "art":         "#7C3AED",
    "museum":      "#7C3AED",
    "nightlife":   "#4338CA",
    "shopping":    "#0E7490",
    "attraction":  "#0F766E",
    "viewpoint":   "#0F766E",
}
_DEFAULT_COLOUR = "#475569"

# Padding (pixels) added around fit_bounds
_FIT_PADDING = (40, 40)
# Maximum zoom level when fit_bounds would zoom in too far (e.g. 2 venues 50 m apart)
_MAX_ZOOM = 16


def render_day_map(
    slots:        list[dict],
    venue_lookup: dict[str, dict],
    day_number:   int   = 1,
    itinerary_id: int   = 0,
    height:       int   = 460,
) -> None:
    """Render a Folium map for one day into the current Streamlit column.

    Parameters
    ----------
    slots:        Itinerary slots for the day.
    venue_lookup: osm_id → venue dict (used to resolve lat/lon).
    day_number:   1-based day index — used to give the map a unique widget
                  key so Streamlit doesn't reuse the same Leaflet instance
                  across tabs (fixes zoom-reset on tab-switch).
    itinerary_id: Itinerary DB id — combined with day_number in the key so
                  a newly generated itinerary always gets a fresh map.
    height:       Pixel height of the embedded map.
    """
    coords = _slot_coords(slots, venue_lookup)
    if not coords:
        return

    # Centre on the mean of all venues
    centre_lat = sum(c[0] for c in coords) / len(coords)
    centre_lon = sum(c[1] for c in coords) / len(coords)

    m = folium.Map(
        location=[centre_lat, centre_lon],
        zoom_start=14,          # overridden by fit_bounds below
        tiles="CartoDB positron",
        control_scale=True,
    )

    # Dashed route line
    if len(coords) > 1:
        folium.PolyLine(
            locations=coords,
            color="#3B82F6",
            weight=2.5,
            opacity=0.7,
            dash_array="8 5",
        ).add_to(m)

    # Numbered markers
    for n, (slot, (lat, lon)) in enumerate(zip(slots, coords), 1):
        colour   = _slot_colour(slot)
        icon_html = _numbered_icon(n, colour)
        popup_html = _popup_html(slot)

        folium.Marker(
            location=[lat, lon],
            icon=folium.DivIcon(
                html=icon_html,
                icon_size=(32, 32),
                icon_anchor=(16, 16),
            ),
            popup=folium.Popup(popup_html, max_width=280),
            tooltip=f"{n}. {slot.get('venue_name', '')}",
        ).add_to(m)

    # Always fit bounds — prevents zoom_start=14 showing on tab switch.
    # For a single venue, pad generously so streets around it are visible.
    if len(coords) == 1:
        lat, lon = coords[0]
        pad = 0.005     # ~500 m each side
        sw = [lat - pad, lon - pad]
        ne = [lat + pad, lon + pad]
    else:
        sw = [min(c[0] for c in coords), min(c[1] for c in coords)]
        ne = [max(c[0] for c in coords), max(c[1] for c in coords)]

    m.fit_bounds([sw, ne], padding=_FIT_PADDING, max_zoom=_MAX_ZOOM)

    # Unique key per (itinerary, day) prevents Streamlit from reusing the
    # same Leaflet widget across tabs — the root cause of the zoom-reset bug.
    widget_key = f"map_{itinerary_id}_day_{day_number}"
    st_folium(
        m,
        height=height,
        use_container_width=True,
        returned_objects=[],
        key=widget_key,
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _slot_coords(
    slots: list[dict], venue_lookup: dict[str, dict]
) -> list[tuple[float, float]]:
    coords: list[tuple[float, float]] = []
    for slot in slots:
        venue = venue_lookup.get(slot.get("osm_id", ""))
        if venue and venue.get("lat") and venue.get("lon"):
            coords.append((venue["lat"], venue["lon"]))
    return coords


def _slot_colour(slot: dict) -> str:
    return _CATEGORY_COLOUR.get(slot.get("category", ""), _DEFAULT_COLOUR)


def _numbered_icon(n: int, colour: str) -> str:
    return (
        f'<div style="'
        f"background:{colour};"
        f"color:#fff;"
        f"border-radius:50%;"
        f"width:32px;height:32px;"
        f"display:flex;align-items:center;justify-content:center;"
        f"font-weight:700;font-size:13px;"
        f"border:2.5px solid #fff;"
        f'box-shadow:0 2px 8px rgba(0,0,0,.35)">'
        f"{n}</div>"
    )


def _popup_html(slot: dict) -> str:
    name  = slot.get("venue_name", "")
    cat   = slot.get("category", "")
    time  = slot.get("time", "")
    desc  = slot.get("description", "")
    dur   = slot.get("duration_minutes")
    if len(desc) > 130:
        desc = desc[:127] + "…"
    dur_str = f"<br><span style='color:#64748B;font-size:11px'>⏱ {dur} min</span>" if dur else ""
    return (
        f"<div style='font-family:sans-serif;padding:2px'>"
        f"<b style='font-size:13px'>{name}</b>"
        f"<br><span style='color:#64748B;font-size:11px'>{cat} · {time}</span>"
        f"{dur_str}"
        f"<br><span style='font-size:12px;color:#334155'>{desc}</span>"
        f"</div>"
    )
