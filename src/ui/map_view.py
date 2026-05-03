"""Folium map rendering for one day's itinerary slots.

Zoom strategy: fit_bounds is NOT used because Leaflet's fitBounds() JS
call fires on map init — when a tab is hidden (display:none, 0×0 px
container) it overwrites zoom_start with a broken value.  Instead,
_bounds_zoom() derives the right zoom level from the coordinate spread
and sets it as zoom_start; location is the centroid.  This works for
all tabs, visible or hidden.
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



def _bounds_zoom(coords: list[tuple[float, float]]) -> int:
    """Return a sensible Leaflet zoom_start from the coordinate spread.

    This is used as the *initial* zoom so that maps in hidden tab panels
    (where Leaflet can't measure the container and fit_bounds silently
    falls back) still open at a reasonable level.
    Thresholds are calibrated for a ~500 px tall map column.
    """
    if len(coords) <= 1:
        return 15
    lat_span = max(c[0] for c in coords) - min(c[0] for c in coords)
    lon_span = max(c[1] for c in coords) - min(c[1] for c in coords)
    span = max(lat_span, lon_span)
    if span < 0.004:  return 15
    if span < 0.008:  return 14
    if span < 0.016:  return 13
    if span < 0.032:  return 12
    if span < 0.065:  return 11
    return 10


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
        zoom_start=_bounds_zoom(coords),   # pre-computed so hidden tabs start correctly
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

    # NOTE: fit_bounds is intentionally NOT called here.
    # Folium's fit_bounds emits a Leaflet fitBounds() JS call that fires on
    # map init. When the tab is hidden (display:none, container size = 0×0),
    # Leaflet cannot compute correct bounds and overwrites zoom_start with a
    # broken value (commonly 0).  Using location + _bounds_zoom() as the sole
    # zoom strategy works correctly for all tabs, visible or hidden.

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
