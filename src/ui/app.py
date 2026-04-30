"""Streamlit entrypoint for the AI Travel Itinerary Generator.

Session-state caching (Phase 2.4): the generated itinerary is stored in
st.session_state after the pipeline completes. Feedback button clicks trigger
a Streamlit rerun, but the form is not re-submitted so preferences is None —
the app reads from session state and re-renders without re-running the pipeline.
A new form submission clears the cache and runs the pipeline fresh.
"""
from __future__ import annotations

import streamlit as st

from src.clustering.geo_clusters import cluster_venues
from src.config import setup_logging
from src.db import get_venues_by_destination, init_db, insert_itinerary
from src.generation.itinerary import USER_ID, build_itinerary
from src.matching.embeddings import embed_and_cache
from src.matching.scoring import match_venues
from src.routing.ors import annotate_itinerary_travel_times
from src.ui.feedback import (
    clear_itinerary_state,
    load_itinerary_state,
    save_itinerary_state,
)
from src.ui.forms import render_preference_form, render_sample_buttons
from src.ui.itinerary_view import render_itinerary
from src.validation.checks import validate_and_fix_itinerary

log = setup_logging()


def main() -> None:
    st.set_page_config(
        page_title="AI Travel Planner",
        page_icon="✈️",
        layout="wide",
        initial_sidebar_state="collapsed",
    )

    init_db()

    st.title("✈️ AI Personal Travel Planner")
    st.caption(
        "Tell us your preferences and get a day-by-day itinerary with real venues, "
        "maps, and travel times — in under 2 minutes."
    )
    st.divider()

    render_sample_buttons()
    st.divider()

    preferences = render_preference_form()

    # ── New form submission → clear cache, run pipeline ───────────────────────
    if preferences is not None:
        clear_itinerary_state()
        _run_pipeline(preferences)

    # ── Render from session state (new generation OR feedback rerun) ──────────
    state = load_itinerary_state()
    if state:
        st.success(
            f"Your {state['preferences']['days']}-day itinerary for "
            f"**{state['preferences']['destination']}** is ready!"
        )
        st.divider()
        render_itinerary(
            itinerary=state["itinerary"],
            clusters=state["clusters"],
            issues=state["issues"],
            itinerary_id=state["itinerary_id"],
            venue_lookup=state["venue_lookup"],
        )
        with st.expander("Preferences (debug)", expanded=False):
            st.json(state["preferences"])


def _run_pipeline(preferences: dict) -> None:
    """Execute all generation steps and store the result in session state."""
    destination = preferences["destination"]

    # ── 1. Venue retrieval ────────────────────────────────────────────────────
    venues = get_venues_by_destination(destination)
    if not venues:
        st.warning(
            f"No cached venues for **{destination}**. "
            'Run `python -m src.ingestion.overpass --destination "Goa, India"` first.'
        )
        return

    # ── 2. Embedding + matching ───────────────────────────────────────────────
    with st.spinner("Matching venues to your preferences…"):
        embed_and_cache(destination)
        venues = get_venues_by_destination(destination)
        matched = match_venues(venues, preferences)

    # ── 3. Geographic clustering ──────────────────────────────────────────────
    with st.spinner("Grouping venues into days…"):
        clusters = cluster_venues(matched, preferences["days"])

    # ── 4. LLM itinerary assembly ─────────────────────────────────────────────
    with st.spinner(
        f"Generating your {preferences['days']}-day itinerary with Groq… "
        "(one call per day)"
    ):
        try:
            itinerary = build_itinerary(clusters, preferences)
        except Exception as exc:
            st.error(f"Itinerary generation failed: {exc}")
            log.exception("build_itinerary failed")
            return

    # ── 5. Travel times ───────────────────────────────────────────────────────
    venue_lookup = {v["osm_id"]: v for c in clusters for v in c}
    with st.spinner("Estimating travel times between venues…"):
        annotate_itinerary_travel_times(itinerary, venue_lookup)

    # ── 6. Validation + auto-fix ──────────────────────────────────────────────
    with st.spinner("Validating itinerary…"):
        itinerary, issues = validate_and_fix_itinerary(
            itinerary, clusters, venue_lookup, preferences
        )

    # ── 7. Persist to SQLite ──────────────────────────────────────────────────
    itinerary_id = insert_itinerary(
        user_id=USER_ID,
        destination=destination,
        preferences=preferences,
        days=preferences["days"],
        output=itinerary,
    )
    log.info(f"Saved itinerary id={itinerary_id}")

    # ── 8. Cache in session state ─────────────────────────────────────────────
    save_itinerary_state(
        itinerary=itinerary,
        clusters=clusters,
        issues=issues,
        itinerary_id=itinerary_id,
        venue_lookup=venue_lookup,
        preferences=preferences,
    )


if __name__ == "__main__":
    main()
