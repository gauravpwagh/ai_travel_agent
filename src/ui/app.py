"""Streamlit entrypoint for the AI Travel Itinerary Generator."""
from __future__ import annotations

import streamlit as st

from src.clustering.geo_clusters import cluster_venues
from src.config import setup_logging
from src.db import get_venues_by_destination, init_db, insert_itinerary
from src.generation.itinerary import USER_ID, build_itinerary
from src.matching.embeddings import embed_and_cache
from src.matching.scoring import match_venues
from src.routing.ors import annotate_itinerary_travel_times
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

    if preferences is None:
        return

    log.info("Preferences submitted: %s", preferences)
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

    itinerary_id = insert_itinerary(
        user_id=USER_ID,
        destination=destination,
        preferences=preferences,
        days=preferences["days"],
        output=itinerary,
    )
    log.info(f"Saved itinerary id={itinerary_id}")

    # ── 7. Display ────────────────────────────────────────────────────────────
    st.success(f"Your {preferences['days']}-day itinerary for **{destination}** is ready!")
    st.divider()

    render_itinerary(itinerary, clusters, issues)

    with st.expander("Preferences (debug)", expanded=False):
        st.json(preferences)


if __name__ == "__main__":
    main()
