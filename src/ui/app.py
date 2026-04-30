"""Streamlit entrypoint for the AI Travel Itinerary Generator."""
from __future__ import annotations

import streamlit as st

from src.clustering.geo_clusters import cluster_venues
from src.config import setup_logging
from src.db import get_venues_by_destination, init_db, insert_itinerary
from src.generation.itinerary import USER_ID, build_itinerary
from src.matching.embeddings import embed_and_cache
from src.matching.scoring import match_venues
from src.ui.forms import render_preference_form, render_sample_buttons

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

    itinerary_id = insert_itinerary(
        user_id=USER_ID,
        destination=destination,
        preferences=preferences,
        days=preferences["days"],
        output=itinerary,
    )
    log.info(f"Saved itinerary id={itinerary_id}")

    # ── 5. Display ────────────────────────────────────────────────────────────
    st.success(f"Your {preferences['days']}-day itinerary for **{destination}** is ready!")
    st.divider()

    _render_itinerary(itinerary)

    with st.expander("Preferences (debug)", expanded=False):
        st.json(preferences)

    st.info("Coming next: interactive map, travel times, and feedback buttons.")


def _render_itinerary(itinerary: list[dict]) -> None:
    day_tabs = st.tabs([f"Day {d['day_number']} — {d.get('theme', '')}" for d in itinerary])
    for tab, day in zip(day_tabs, itinerary):
        with tab:
            for slot in day.get("slots", []):
                col_time, col_body = st.columns([1, 5])
                with col_time:
                    st.markdown(f"### {slot.get('time', '')}")
                    mins = slot.get("duration_minutes")
                    if mins:
                        st.caption(f"{mins} min")
                with col_body:
                    cats = slot.get("category", "")
                    st.markdown(f"**{slot['venue_name']}** &nbsp; `{cats}`")
                    st.write(slot.get("description", ""))
                    note = slot.get("travel_note")
                    if note:
                        st.caption(f"🚶 {note}")
                st.divider()


if __name__ == "__main__":
    main()
