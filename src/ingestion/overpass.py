"""Overpass API venue ingestion (Phase 1.1).

Fetches POIs (tourism, amenity, leisure, shop) within a radius of a destination,
parses OSM tags into structured fields, and caches in SQLite.

Usage:
    python -m src.ingestion.overpass --destination "Goa, India"
    python -m src.ingestion.overpass --destination "Mumbai, India" --radius 20000
"""
from __future__ import annotations

import argparse
from typing import Any

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from src.config import (
    USER_AGENT,
    VENUE_FETCH_RADIUS_M,
    setup_logging,
)
from src.db import init_db, insert_venue, venue_count
from src.ingestion.nominatim import geocode

log = setup_logging()

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# OSM keys we treat as relevant POIs. Each maps to a normalized category.
# Tweak as you discover gaps in your destination's data.
RELEVANT_TAGS: dict[str, dict[str, str]] = {
    "tourism": {
        "attraction": "attraction",
        "museum": "museum",
        "viewpoint": "viewpoint",
        "gallery": "art",
        "artwork": "art",
        "zoo": "attraction",
        "theme_park": "attraction",
        "aquarium": "attraction",
    },
    "amenity": {
        "restaurant": "food",
        "cafe": "cafe",
        "bar": "nightlife",
        "pub": "nightlife",
        "nightclub": "nightlife",
        "ice_cream": "cafe",
        "fast_food": "food",
        "food_court": "food",
        "marketplace": "shopping",
        "place_of_worship": "history",
    },
    "leisure": {
        "park": "nature",
        "garden": "nature",
        "beach_resort": "beach",
        "nature_reserve": "nature",
    },
    "natural": {
        "beach": "beach",
        "peak": "nature",
        "waterfall": "nature",
    },
    "historic": {
        "monument": "history",
        "ruins": "history",
        "castle": "history",
        "fort": "history",
        "memorial": "history",
        "archaeological_site": "history",
    },
    "shop": {
        "mall": "shopping",
        "department_store": "shopping",
        "gift": "shopping",
        "art": "shopping",
        "craft": "shopping",
    },
}


def build_overpass_query(lat: float, lon: float, radius_m: int) -> str:
    """Construct an Overpass QL query for relevant POIs around (lat, lon)."""
    clauses: list[str] = []
    for key, values in RELEVANT_TAGS.items():
        regex = "|".join(values.keys())
        # nodes, ways, relations — capture all three
        for typ in ("node", "way", "relation"):
            clauses.append(
                f'{typ}["{key}"~"^({regex})$"](around:{radius_m},{lat},{lon});'
            )
    body = "\n  ".join(clauses)
    return f"""
[out:json][timeout:60];
(
  {body}
);
out center tags;
""".strip()


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=20))
def fetch_overpass(query: str) -> dict[str, Any]:
    log.info("Querying Overpass API…")
    resp = requests.post(
        OVERPASS_URL,
        data={"data": query},
        headers={"User-Agent": USER_AGENT},
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()


def categorize(tags: dict[str, str]) -> list[str]:
    """Return list of normalized category labels from raw OSM tags."""
    cats: set[str] = set()
    for key, value_map in RELEVANT_TAGS.items():
        if key in tags and tags[key] in value_map:
            cats.add(value_map[tags[key]])
    return sorted(cats)


def estimate_price_level(tags: dict[str, str]) -> int | None:
    """Map osm 'price' or 'fee' tags to a 1-4 scale. Returns None if unknown.

    OSM doesn't have a strong price signal, so this is best-effort. Phase 2
    can enrich via Foursquare if needed.
    """
    if "price" in tags:
        # Some POIs use "$", "$$", etc.
        symbol = tags["price"]
        if isinstance(symbol, str) and set(symbol) == {"$"}:
            return min(len(symbol), 4)
    return None


def build_description(name: str, cats: list[str], tags: dict[str, str]) -> str:
    """Build a short text description used for embedding.

    Concatenates: name, categories, cuisine (if any), notable boolean tags
    (outdoor_seating, wheelchair, etc.), and addr:suburb if present.
    """
    parts: list[str] = [name]

    if cats:
        parts.append(", ".join(cats))

    if "cuisine" in tags:
        # Cuisines may be ;-separated in OSM
        cuisines = tags["cuisine"].replace(";", ", ")
        parts.append(f"cuisine: {cuisines}")

    notable_flags = [
        "outdoor_seating",
        "takeaway",
        "vegetarian",
        "vegan",
        "wheelchair",
        "rooftop",
        "view",
        "wifi",
    ]
    flags_present = [f for f in notable_flags if tags.get(f) in ("yes", "only")]
    if flags_present:
        parts.append(", ".join(flags_present))

    suburb = tags.get("addr:suburb") or tags.get("addr:city")
    if suburb:
        parts.append(f"in {suburb}")

    return " | ".join(parts)


def parse_element(el: dict[str, Any], destination: str) -> dict[str, Any] | None:
    """Convert one Overpass element into our venue dict, or None if unusable."""
    tags = el.get("tags", {})
    name = tags.get("name") or tags.get("name:en")
    if not name:
        return None

    # Coords: nodes have lat/lon directly; ways/relations have a 'center'
    if el["type"] == "node":
        lat = el.get("lat")
        lon = el.get("lon")
    else:
        center = el.get("center", {})
        lat = center.get("lat")
        lon = center.get("lon")

    if lat is None or lon is None:
        return None

    cats = categorize(tags)
    if not cats:
        return None  # not a category we care about

    osm_id = f"{el['type']}/{el['id']}"

    return {
        "osm_id": osm_id,
        "destination": destination,
        "name": name,
        "lat": float(lat),
        "lon": float(lon),
        "categories": cats,
        "tags": tags,
        "description": build_description(name, cats, tags),
        "rating": None,  # OSM has no rating; Phase 2 enriches via Foursquare
        "price_level": estimate_price_level(tags),
        "opening_hours": tags.get("opening_hours"),
    }


def ingest_destination(destination: str, radius_m: int = VENUE_FETCH_RADIUS_M) -> int:
    """Fetch and cache venues for a destination. Returns number newly inserted."""
    init_db()

    existing = venue_count(destination)
    if existing > 0:
        log.info(f"Already have {existing} cached venues for '{destination}'.")
        log.info("Delete from venues table first if you want to re-fetch.")
        return 0

    lat, lon, _bbox = geocode(destination)
    query = build_overpass_query(lat, lon, radius_m)
    data = fetch_overpass(query)

    elements = data.get("elements", [])
    log.info(f"Overpass returned {len(elements)} raw elements")

    inserted = 0
    skipped = 0
    for el in elements:
        venue = parse_element(el, destination)
        if venue is None:
            skipped += 1
            continue
        if insert_venue(venue) is not None:
            inserted += 1

    log.info(
        f"Ingested {inserted} venues for '{destination}' "
        f"({skipped} skipped: no name/coords/category)"
    )
    return inserted


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch and cache OSM venues")
    parser.add_argument(
        "--destination",
        required=True,
        help='e.g. "Goa, India" or "Mumbai, India"',
    )
    parser.add_argument(
        "--radius",
        type=int,
        default=VENUE_FETCH_RADIUS_M,
        help="Search radius in meters (default 15000)",
    )
    args = parser.parse_args()

    n = ingest_destination(args.destination, args.radius)
    print(f"Done. Inserted {n} venues for '{args.destination}'.")


if __name__ == "__main__":
    main()
