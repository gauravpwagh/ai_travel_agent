"""Streamlit entrypoint for the AI Travel Itinerary Generator."""
from __future__ import annotations

import streamlit as st

from src.config import setup_logging
from src.db import get_venues_by_destination, init_db
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

    # ── Header ────────────────────────────────────────────────────────────────
    st.title("✈️ AI Personal Travel Planner")
    st.caption(
        "Tell us your preferences and get a day-by-day itinerary with real venues, "
        "maps, and travel times — in under 2 minutes."
    )
    st.divider()

    # ── Preset buttons ────────────────────────────────────────────────────────
    render_sample_buttons()
    st.divider()

    # ── Preference form ───────────────────────────────────────────────────────
    preferences = render_preference_form()

    # ── Matching pipeline (Phases 1.3) ────────────────────────────────────────
    if preferences is not None:
        log.info("Preferences submitted: %s", preferences)
        destination = preferences["destination"]

        venues = get_venues_by_destination(destination)
        if not venues:
            st.warning(
                f"No cached venues for **{destination}**. "
                "Run `python -m src.ingestion.overpass --destination \"Goa, India\"` first."
            )
            return

        with st.spinner("Embedding venues and matching preferences…"):
            embed_and_cache(destination)
            venues = get_venues_by_destination(destination)
            matched = match_venues(venues, preferences)

        st.success(f"Matched **{len(matched)}** venues to your preferences.")

        with st.expander("Top matched venues (debug)", expanded=False):
            for v in matched[:10]:
                st.write(
                    f"**{v['name']}** — {', '.join(v['categories'])} "
                    f"| score: {v.get('similarity_score', 0):.3f}"
                )

        with st.expander("Preference object (debug)", expanded=False):
            st.json(preferences)

        st.info("Next: geographic clustering → LLM itinerary assembly → map display.")


if __name__ == "__main__":
    main()
