"""Nominatim (OSM) geocoder. Free, no key. Rate limit: 1 req/sec.

Usage:
    from src.ingestion.nominatim import geocode
    lat, lon, bbox = geocode("Goa, India")
"""
from __future__ import annotations

import time

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from src.config import USER_AGENT, setup_logging

log = setup_logging()

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
_LAST_REQUEST_TS = 0.0


def _rate_limit() -> None:
    """Nominatim policy: max 1 req/sec."""
    global _LAST_REQUEST_TS
    elapsed = time.time() - _LAST_REQUEST_TS
    if elapsed < 1.1:
        time.sleep(1.1 - elapsed)
    _LAST_REQUEST_TS = time.time()


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
def geocode(query: str) -> tuple[float, float, list[float]]:
    """Resolve a place name to (lat, lon, bbox=[s,n,w,e]).

    Raises if the query returns no results.
    """
    _rate_limit()
    resp = requests.get(
        NOMINATIM_URL,
        params={
            "q": query,
            "format": "json",
            "limit": 1,
        },
        headers={"User-Agent": USER_AGENT},
        timeout=15,
    )
    resp.raise_for_status()
    results = resp.json()
    if not results:
        raise ValueError(f"No geocoding result for: {query}")

    r = results[0]
    lat = float(r["lat"])
    lon = float(r["lon"])
    # Nominatim bbox order: [south, north, west, east]
    bbox = [float(x) for x in r["boundingbox"]]
    log.info(f"Geocoded '{query}' -> ({lat:.4f}, {lon:.4f})")
    return lat, lon, bbox


if __name__ == "__main__":
    import sys

    q = sys.argv[1] if len(sys.argv) > 1 else "Goa, India"
    lat, lon, bbox = geocode(q)
    print(f"{q}: lat={lat}, lon={lon}, bbox={bbox}")
