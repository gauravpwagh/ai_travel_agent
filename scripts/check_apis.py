"""Phase 0 'hello world' — verify each API responds.

Run after filling in .env:
    python scripts/check_apis.py
"""
from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests

from src.config import GROQ_API_KEY, GROQ_MODEL, ORS_API_KEY, USER_AGENT


def check(label: str, fn) -> bool:
    print(f"  [{label}] checking… ", end="", flush=True)
    try:
        fn()
        print("OK")
        return True
    except Exception as e:  # noqa: BLE001
        print(f"FAIL — {type(e).__name__}: {e}")
        return False


def check_nominatim() -> None:
    r = requests.get(
        "https://nominatim.openstreetmap.org/search",
        params={"q": "Goa, India", "format": "json", "limit": 1},
        headers={"User-Agent": USER_AGENT},
        timeout=15,
    )
    r.raise_for_status()
    if not r.json():
        raise RuntimeError("Empty Nominatim response")


def check_overpass() -> None:
    # Very small query just to confirm the endpoint responds
    q = '[out:json][timeout:10];node["amenity"="cafe"](15.49,73.82,15.50,73.83);out 1;'
    r = requests.post(
        "https://overpass-api.de/api/interpreter",
        data={"data": q},
        headers={"User-Agent": USER_AGENT},
        timeout=30,
    )
    r.raise_for_status()
    r.json()  # must be valid JSON


def check_open_meteo() -> None:
    r = requests.get(
        "https://api.open-meteo.com/v1/forecast",
        params={"latitude": 15.5, "longitude": 73.8, "current_weather": "true"},
        timeout=15,
    )
    r.raise_for_status()
    if "current_weather" not in r.json():
        raise RuntimeError("Unexpected Open-Meteo response")


def check_groq() -> None:
    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY not set in .env")
    from groq import Groq

    client = Groq(api_key=GROQ_API_KEY)
    resp = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[{"role": "user", "content": "Reply with exactly the word: pong"}],
        max_tokens=10,
    )
    text = resp.choices[0].message.content or ""
    if "pong" not in text.lower():
        raise RuntimeError(f"Unexpected Groq response: {text!r}")


def check_ors() -> None:
    if not ORS_API_KEY:
        # ORS isn't strictly required for Phase 1, only Phase 2.2
        raise RuntimeError("ORS_API_KEY not set (skip if not on Phase 2 yet)")
    r = requests.get(
        "https://api.openrouteservice.org/v2/directions/foot-walking",
        params={
            "api_key": ORS_API_KEY,
            "start": "73.8278,15.4909",
            "end": "73.8378,15.5009",
        },
        timeout=15,
    )
    r.raise_for_status()


def main() -> int:
    print("Phase 0 API check\n" + "=" * 40)
    results = {
        "Nominatim (OSM)": check("Nominatim", check_nominatim),
        "Overpass (OSM)": check("Overpass ", check_overpass),
        "Open-Meteo": check("Weather  ", check_open_meteo),
        "Groq LLM": check("Groq     ", check_groq),
        "OpenRouteService": check("ORS      ", check_ors),
    }
    print("=" * 40)
    failed = [k for k, ok in results.items() if not ok]
    if failed:
        print(f"\n{len(failed)} check(s) failed: {', '.join(failed)}")
        print("ORS can be skipped for Phase 1 if you haven't signed up yet.")
        return 1
    print("\nAll checks passed. Ready for Phase 1.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
