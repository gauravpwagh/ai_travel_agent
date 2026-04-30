"""SQLite schema initialization and helpers.

Usage:
    python -m src.db init      # create tables
    python -m src.db reset     # drop and recreate
"""
from __future__ import annotations

import json
import sqlite3
import sys
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Iterator

from src.config import DB_PATH, setup_logging

log = setup_logging()

SCHEMA = """
CREATE TABLE IF NOT EXISTS venues (
    id INTEGER PRIMARY KEY,
    osm_id TEXT UNIQUE,
    destination TEXT,
    name TEXT NOT NULL,
    lat REAL NOT NULL,
    lon REAL NOT NULL,
    categories TEXT,          -- JSON array
    tags TEXT,                -- JSON, raw OSM tags
    description TEXT,         -- Built for embedding
    rating REAL,
    price_level INTEGER,      -- 1-4
    opening_hours TEXT,       -- OSM format
    embedding BLOB,           -- Cached vector
    fetched_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS itineraries (
    id INTEGER PRIMARY KEY,
    user_id TEXT,
    destination TEXT,
    preferences TEXT,         -- JSON
    days INTEGER,
    output TEXT,              -- Full itinerary JSON
    created_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY,
    itinerary_id INTEGER,
    venue_id INTEGER,
    day_number INTEGER,
    action TEXT,              -- 'thumbs_up', 'thumbs_down', 'swap'
    created_at TIMESTAMP,
    FOREIGN KEY (itinerary_id) REFERENCES itineraries(id),
    FOREIGN KEY (venue_id) REFERENCES venues(id)
);

CREATE TABLE IF NOT EXISTS travel_times (
    id INTEGER PRIMARY KEY,
    origin_osm_id TEXT NOT NULL,
    dest_osm_id TEXT NOT NULL,
    profile TEXT NOT NULL,          -- 'foot-walking' | 'driving-car'
    duration_s INTEGER,             -- seconds
    distance_m INTEGER,             -- metres
    source TEXT,                    -- 'ors' | 'haversine'
    fetched_at TIMESTAMP,
    UNIQUE(origin_osm_id, dest_osm_id, profile)
);

CREATE INDEX IF NOT EXISTS idx_venues_destination ON venues(destination);
CREATE INDEX IF NOT EXISTS idx_feedback_itinerary ON feedback(itinerary_id);
CREATE INDEX IF NOT EXISTS idx_travel_times ON travel_times(origin_osm_id, dest_osm_id, profile);
"""


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    """Context manager for SQLite connection with row factory."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    """Create tables if they don't exist."""
    with connect() as conn:
        conn.executescript(SCHEMA)
    log.info(f"Initialized DB at {DB_PATH}")


def reset_db() -> None:
    """Drop all tables and recreate. DESTRUCTIVE."""
    with connect() as conn:
        conn.executescript("""
            DROP TABLE IF EXISTS feedback;
            DROP TABLE IF EXISTS itineraries;
            DROP TABLE IF EXISTS venues;
        """)
    log.warning("Dropped all tables")
    init_db()


def insert_venue(venue: dict[str, Any]) -> int | None:
    """Insert a venue; returns rowid or None if duplicate osm_id.

    Expected keys: osm_id, destination, name, lat, lon, categories (list),
    tags (dict), description, rating, price_level, opening_hours.
    """
    with connect() as conn:
        try:
            cursor = conn.execute(
                """
                INSERT INTO venues (
                    osm_id, destination, name, lat, lon,
                    categories, tags, description,
                    rating, price_level, opening_hours, fetched_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    venue["osm_id"],
                    venue["destination"],
                    venue["name"],
                    venue["lat"],
                    venue["lon"],
                    json.dumps(venue.get("categories", [])),
                    json.dumps(venue.get("tags", {})),
                    venue.get("description"),
                    venue.get("rating"),
                    venue.get("price_level"),
                    venue.get("opening_hours"),
                    datetime.utcnow().isoformat(),
                ),
            )
            return cursor.lastrowid
        except sqlite3.IntegrityError:
            # Already cached
            return None


def get_venues_by_destination(destination: str) -> list[dict[str, Any]]:
    """Return all cached venues for a destination."""
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM venues WHERE destination = ?",
            (destination,),
        ).fetchall()
    return [_row_to_venue(r) for r in rows]


def insert_itinerary(
    user_id: str,
    destination: str,
    preferences: dict[str, Any],
    days: int,
    output: list[dict[str, Any]],
) -> int:
    """Persist a generated itinerary. Returns the new row id."""
    with connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO itineraries (user_id, destination, preferences, days, output, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                destination,
                json.dumps(preferences),
                days,
                json.dumps(output),
                datetime.utcnow().isoformat(),
            ),
        )
        return cursor.lastrowid


def get_travel_time(
    origin_osm_id: str, dest_osm_id: str, profile: str
) -> dict[str, Any] | None:
    """Return cached travel-time row or None on cache miss."""
    with connect() as conn:
        row = conn.execute(
            """
            SELECT duration_s, distance_m, source
            FROM travel_times
            WHERE origin_osm_id = ? AND dest_osm_id = ? AND profile = ?
            """,
            (origin_osm_id, dest_osm_id, profile),
        ).fetchone()
    return dict(row) if row else None


def insert_travel_time(
    origin_osm_id: str,
    dest_osm_id: str,
    profile: str,
    duration_s: int,
    distance_m: int,
    source: str,
) -> None:
    """Upsert a travel-time result into the cache."""
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO travel_times
                (origin_osm_id, dest_osm_id, profile, duration_s, distance_m, source, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(origin_osm_id, dest_osm_id, profile) DO UPDATE SET
                duration_s = excluded.duration_s,
                distance_m = excluded.distance_m,
                source     = excluded.source,
                fetched_at = excluded.fetched_at
            """,
            (
                origin_osm_id,
                dest_osm_id,
                profile,
                duration_s,
                distance_m,
                source,
                datetime.utcnow().isoformat(),
            ),
        )


def update_venue_embedding(venue_id: int, embedding_bytes: bytes) -> None:
    """Write a cached embedding BLOB for a venue row."""
    with connect() as conn:
        conn.execute(
            "UPDATE venues SET embedding = ? WHERE id = ?",
            (embedding_bytes, venue_id),
        )


def venue_count(destination: str) -> int:
    with connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM venues WHERE destination = ?",
            (destination,),
        ).fetchone()
    return row["n"] if row else 0


def _row_to_venue(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    d["categories"] = json.loads(d["categories"]) if d.get("categories") else []
    d["tags"] = json.loads(d["tags"]) if d.get("tags") else {}
    return d


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m src.db [init|reset]")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "init":
        init_db()
        print(f"DB initialized at {DB_PATH}")
    elif cmd == "reset":
        reset_db()
        print(f"DB reset at {DB_PATH}")
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()
