"""Folium map rendering for one day's itinerary slots.

Produces a map with:
- Numbered circular markers in category colour
- Dashed polyline connecting venues in visit order
- Popup per marker: name, category, description snippet

Usage:
    from src.ui.map_view import render_day_map
    render_day_map(slots, venue_lookup)   # renders directly into Streamlit
"""
from __future__ import annotations

import folium
from streamlit_folium import st_folium

# ── Category → marker colour (Folium named colours) ──────────────────────────
_CATEGORY_COLOUR: dict[str, str] = {
    "food":        "#e05c2a",
    "cafe":        "#f0a500",
    "beach":       "#1a8fc1",
    "nature":      "#2e8b57",
    "history":     "#8b1a1a",
    "art":         "#7b2f8e",
    "museum":      "#7b2f8e",
    "nightlife":   "#2c2c8e",
    "shopping":    "#1a5276",
    "attraction":  "#1f7a5e",
    "viewpoint":   "#1f7a5e",
}
_DEFAULT_COLOUR = "#555555"


def render_day_map(
    slots: list[dict],
    venue_lookup: dict[str, dict],
    height: int = 440,
) -> None:
    """Render a Folium map for one day's slots into the current Streamlit column."""
    coords = _slot_coords(slots, venue_lookup)
    if not coords:
        return

    centre_lat = sum(c[0] for c in coords) / len(coords)
    centre_lon = sum(c[1] for c in coords) / len(coords)

    m = folium.Map(
        location=[centre_lat, centre_lon],
        zoom_start=14,
        tiles="CartoDB positron",
    )

    # Route line connecting venues in order
    if len(coords) > 1:
        folium.PolyLine(
            locations=coords,
            color="#4a90d9",
            weight=2.5,
            opacity=0.75,
            dash_array="8 4",
        ).add_to(m)

    # Numbered markers
    for n, (slot, (lat, lon)) in enumerate(zip(slots, coords), 1):
        colour = _slot_colour(slot)
        icon_html = _numbered_icon(n, colour)
        popup_html = _popup_html(slot)

        folium.Marker(
            location=[lat, lon],
            icon=folium.DivIcon(
                html=icon_html,
                icon_size=(30, 30),
                icon_anchor=(15, 15),
            ),
            popup=folium.Popup(popup_html, max_width=260),
            tooltip=f"{n}. {slot.get('venue_name', '')}",
        ).add_to(m)

    # Auto-fit bounds
    if len(coords) > 1:
        m.fit_bounds(
            [[min(c[0] for c in coords), min(c[1] for c in coords)],
             [max(c[0] for c in coords), max(c[1] for c in coords)]],
            padding=(30, 30),
        )

    st_folium(m, height=height, use_container_width=True, returned_objects=[])


# ── Helpers ───────────────────────────────────────────────────────────────────

def _slot_coords(
    slots: list[dict], venue_lookup: dict[str, dict]
) -> list[tuple[float, float]]:
    """Return (lat, lon) for each slot, skipping any without coordinates."""
    coords: list[tuple[float, float]] = []
    for slot in slots:
        venue = venue_lookup.get(slot.get("osm_id", ""))
        if venue and venue.get("lat") and venue.get("lon"):
            coords.append((venue["lat"], venue["lon"]))
    return coords


def _slot_colour(slot: dict) -> str:
    cat = slot.get("category", "")
    return _CATEGORY_COLOUR.get(cat, _DEFAULT_COLOUR)


def _numbered_icon(n: int, colour: str) -> str:
    return (
        f'<div style="'
        f"background:{colour};"
        f"color:#fff;"
        f"border-radius:50%;"
        f"width:30px;height:30px;"
        f"display:flex;align-items:center;justify-content:center;"
        f"font-weight:700;font-size:13px;"
        f"border:2px solid #fff;"
        f'box-shadow:0 2px 5px rgba(0,0,0,.45)">'
        f"{n}</div>"
    )


def _popup_html(slot: dict) -> str:
    name = slot.get("venue_name", "")
    cat = slot.get("category", "")
    time = slot.get("time", "")
    desc = slot.get("description", "")
    # Truncate description for popup readability
    if len(desc) > 120:
        desc = desc[:117] + "…"
    return (
        f"<b>{name}</b><br>"
        f"<span style='color:#888;font-size:11px'>{cat} · {time}</span><br>"
        f"<span style='font-size:12px'>{desc}</span>"
    )
