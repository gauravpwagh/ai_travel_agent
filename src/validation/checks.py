"""Validation layer — four programmatic checks + auto-fix loop.

Checks
------
hallucination   ERROR    Slot osm_id not in the candidate cluster set.
                         Triggers LLM regeneration (up to MAX_FIX_ATTEMPTS).
opening_hours   WARNING  Slot scheduled outside parsed venue opening hours.
transit         WARNING  Day total transit time exceeds TRANSIT_WARN_MIN.
rating          WARNING  Venue rating below MIN_RATING (only when rating known).

Usage
-----
    from src.validation.checks import validate_and_fix_itinerary

    itinerary, issues = validate_and_fix_itinerary(
        itinerary, clusters, venue_lookup, preferences
    )
    # issues: list[ValidationIssue]
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from src.config import setup_logging
from src.routing.ors import day_total_transit_minutes

log = setup_logging()

MAX_FIX_ATTEMPTS  = 2
TRANSIT_WARN_MIN  = 90   # flag days where total walking time exceeds this
MIN_RATING        = 3.5  # only checked when venue.rating is not None


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class ValidationIssue:
    check:      str           # 'hallucination' | 'opening_hours' | 'transit' | 'rating'
    severity:   str           # 'error' | 'warning'
    day_number: int
    venue_name: str | None
    message:    str
    auto_fixed: bool = field(default=False)


# ── Public API ────────────────────────────────────────────────────────────────

def validate_and_fix_itinerary(
    itinerary:    list[dict],
    clusters:     list[list[dict]],
    venue_lookup: dict[str, dict],
    preferences:  dict,
) -> tuple[list[dict], list[ValidationIssue]]:
    """Run all checks on every day. Regenerate days that have hallucination errors.

    Returns the (possibly repaired) itinerary and the full issue list.
    Travel-time annotation must have already run so the transit check has data.
    """
    # Import here to avoid circular import at module load time
    from src.generation.itinerary import regenerate_day

    all_issues: list[ValidationIssue] = []

    for i, day in enumerate(itinerary):
        cluster = clusters[i] if i < len(clusters) else []
        valid_osm_ids = {v["osm_id"] for v in cluster}

        day_issues = _check_day(day, valid_osm_ids, venue_lookup)
        errors     = [iss for iss in day_issues if iss.severity == "error"]

        if errors:
            fixed = False
            for attempt in range(1, MAX_FIX_ATTEMPTS + 1):
                log.info(
                    f"Day {day['day_number']}: {len(errors)} error(s) — "
                    f"regeneration attempt {attempt}/{MAX_FIX_ATTEMPTS}"
                )
                new_day    = regenerate_day(day["day_number"], cluster, preferences)
                new_issues = _check_day(new_day, valid_osm_ids, venue_lookup)
                new_errors = [iss for iss in new_issues if iss.severity == "error"]

                if not new_errors:
                    itinerary[i] = new_day
                    # Mark original errors as auto-fixed; keep new (warning) issues
                    for iss in errors:
                        iss.auto_fixed = True
                    day_issues = [*errors, *new_issues]
                    fixed = True
                    log.info(f"Day {day['day_number']}: auto-fixed after attempt {attempt}.")
                    break

            if not fixed:
                log.warning(
                    f"Day {day['day_number']}: could not auto-fix after "
                    f"{MAX_FIX_ATTEMPTS} attempts — keeping best available."
                )

        all_issues.extend(day_issues)

    _log_summary(all_issues)
    return itinerary, all_issues


def run_checks_only(
    itinerary:    list[dict],
    clusters:     list[list[dict]],
    venue_lookup: dict[str, dict],
) -> list[ValidationIssue]:
    """Read-only check — no regeneration. Useful for testing."""
    issues: list[ValidationIssue] = []
    for i, day in enumerate(itinerary):
        cluster       = clusters[i] if i < len(clusters) else []
        valid_osm_ids = {v["osm_id"] for v in cluster}
        issues.extend(_check_day(day, valid_osm_ids, venue_lookup))
    return issues


# ── Per-day dispatcher ────────────────────────────────────────────────────────

def _check_day(
    day:          dict,
    valid_osm_ids: set[str],
    venue_lookup:  dict[str, dict],
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    issues.extend(_check_hallucinations(day, valid_osm_ids))
    issues.extend(_check_opening_hours(day, venue_lookup))
    issues.extend(_check_transit(day))
    issues.extend(_check_ratings(day, venue_lookup))
    return issues


# ── Check 1: Hallucination ────────────────────────────────────────────────────

def _check_hallucinations(day: dict, valid_osm_ids: set[str]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for slot in day.get("slots", []):
        osm_id = slot.get("osm_id", "")
        if osm_id not in valid_osm_ids:
            issues.append(ValidationIssue(
                check="hallucination",
                severity="error",
                day_number=day["day_number"],
                venue_name=slot.get("venue_name"),
                message=(
                    f"'{slot.get('venue_name')}' (osm_id={osm_id!r}) was not in "
                    "the candidate set — hallucinated venue."
                ),
            ))
    return issues


# ── Check 2: Opening hours ────────────────────────────────────────────────────

def _check_opening_hours(day: dict, venue_lookup: dict[str, dict]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for slot in day.get("slots", []):
        venue = venue_lookup.get(slot.get("osm_id", ""))
        if not venue:
            continue
        hours_str = venue.get("opening_hours")
        if not hours_str:
            continue  # no data → can't verify, don't flag

        parsed = _parse_hours(hours_str)
        if parsed is None:
            continue  # too complex to parse → skip

        open_min, close_min = parsed
        slot_time = slot.get("time", "")
        slot_min  = _time_to_minutes(slot_time)
        if slot_min is None:
            continue

        # Venue closed at scheduled time
        if not (open_min <= slot_min < close_min):
            open_hm  = _minutes_to_hhmm(open_min)
            close_hm = _minutes_to_hhmm(close_min)
            issues.append(ValidationIssue(
                check="opening_hours",
                severity="warning",
                day_number=day["day_number"],
                venue_name=slot.get("venue_name"),
                message=(
                    f"'{slot.get('venue_name')}' scheduled at {slot_time} but "
                    f"hours suggest {open_hm}–{close_hm}."
                ),
            ))
    return issues


# ── Check 3: Transit overflow ─────────────────────────────────────────────────

def _check_transit(day: dict) -> list[ValidationIssue]:
    total_min = day_total_transit_minutes(day)
    if total_min >= TRANSIT_WARN_MIN:
        return [ValidationIssue(
            check="transit",
            severity="warning",
            day_number=day["day_number"],
            venue_name=None,
            message=(
                f"Total estimated transit is {total_min} min "
                f"(threshold {TRANSIT_WARN_MIN} min). Consider removing a stop."
            ),
        )]
    return []


# ── Check 4: Rating ───────────────────────────────────────────────────────────

def _check_ratings(day: dict, venue_lookup: dict[str, dict]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for slot in day.get("slots", []):
        venue  = venue_lookup.get(slot.get("osm_id", ""))
        rating = venue.get("rating") if venue else None
        if rating is not None and rating < MIN_RATING:
            issues.append(ValidationIssue(
                check="rating",
                severity="warning",
                day_number=day["day_number"],
                venue_name=slot.get("venue_name"),
                message=(
                    f"'{slot.get('venue_name')}' has rating {rating:.1f} "
                    f"(minimum {MIN_RATING})."
                ),
            ))
    return issues


# ── Opening-hours parser ──────────────────────────────────────────────────────

def _parse_hours(hours_str: str) -> tuple[int, int] | None:
    """Parse a simplified OSM opening_hours string → (open_min, close_min).

    Returns None when the format is too complex to parse confidently.
    Handles:
      24/7                → (0, 1440)
      sunrise-sunset      → (360, 1200) approximation
      HH:MM-HH:MM         → direct
      <day-spec> HH:MM-HH:MM  → strip day spec, use time range
    Midnight-crossing ranges (e.g. 20:00-02:00) are expanded to (open, 1440).
    """
    s = hours_str.strip()

    if s.lower() == "24/7":
        return (0, 1440)

    if re.search(r"sunrise|sunset", s, re.I):
        return (360, 1200)  # 06:00 – 20:00

    # Find first HH:MM-HH:MM pattern in the string
    m = re.search(r"(\d{1,2}):(\d{2})\s*[-–]\s*(\d{1,2}):(\d{2})", s)
    if not m:
        return None

    open_min  = int(m.group(1)) * 60 + int(m.group(2))
    close_min = int(m.group(3)) * 60 + int(m.group(4))

    if close_min < open_min:
        # Midnight-crossing: treat as open until end of day
        close_min = 1440

    return (open_min, close_min)


def _time_to_minutes(t: str) -> int | None:
    """'HH:MM' → minutes since midnight, or None on bad input."""
    m = re.match(r"^(\d{1,2}):(\d{2})$", t.strip())
    if not m:
        return None
    return int(m.group(1)) * 60 + int(m.group(2))


def _minutes_to_hhmm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


# ── Summary logging ───────────────────────────────────────────────────────────

def _log_summary(issues: list[ValidationIssue]) -> None:
    errors   = [iss for iss in issues if iss.severity == "error"]
    warnings = [iss for iss in issues if iss.severity == "warning"]
    fixed    = [iss for iss in errors  if iss.auto_fixed]
    log.info(
        f"Validation complete — "
        f"{len(errors)} error(s) ({len(fixed)} auto-fixed), "
        f"{len(warnings)} warning(s)."
    )
    for iss in issues:
        level = "INFO" if iss.auto_fixed else ("ERROR" if iss.severity == "error" else "WARNING")
        log.log(
            __import__("logging").getLevelName(level),
            f"  [{iss.check}] Day {iss.day_number} {iss.venue_name or ''}: {iss.message}"
            + (" [AUTO-FIXED]" if iss.auto_fixed else ""),
        )
