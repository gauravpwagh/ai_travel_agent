"""Central configuration: env loading, paths, constants."""
from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

# Project paths
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
CACHE_DIR = DATA_DIR / "cache"
LOG_DIR = DATA_DIR / "logs"
DB_PATH = DATA_DIR / "travel.db"

for d in (DATA_DIR, CACHE_DIR, LOG_DIR):
    d.mkdir(parents=True, exist_ok=True)

# Load .env
load_dotenv(ROOT / ".env")

# API keys
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
ORS_API_KEY = os.getenv("ORS_API_KEY", "")
FOURSQUARE_API_KEY = os.getenv("FOURSQUARE_API_KEY", "")
GOOGLE_PLACES_API_KEY = os.getenv("GOOGLE_PLACES_API_KEY", "")

# Defaults
DEFAULT_DESTINATION = os.getenv("DEFAULT_DESTINATION", "Goa, India")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Model config
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
GROQ_MODEL = "llama-3.3-70b-versatile"

# Pipeline tuning
VENUE_FETCH_RADIUS_M = 15_000  # 15 km around city center
MIN_VENUES_PER_CITY = 100
MAX_VENUES_PER_DAY = 6
TOP_N_AFTER_RANKING = 50

# User-Agent for OSM/Nominatim (required by their policy)
USER_AGENT = "travel-itinerary-prototype/0.1 (academic project)"


def setup_logging() -> logging.Logger:
    """Configure root logger to write to data/logs/app.log."""
    logger = logging.getLogger("travel_agent")
    if logger.handlers:
        return logger

    logger.setLevel(LOG_LEVEL)
    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )

    file_handler = logging.FileHandler(LOG_DIR / "app.log")
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(fmt)
    logger.addHandler(stream_handler)

    return logger


def assert_keys(required: list[str]) -> None:
    """Fail fast if required keys are missing."""
    missing = [k for k in required if not os.getenv(k)]
    if missing:
        raise RuntimeError(
            f"Missing env vars: {missing}. Copy .env.example to .env and fill in."
        )
