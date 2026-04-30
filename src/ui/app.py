"""Streamlit entrypoint for the AI Travel Itinerary Generator."""
from __future__ import annotations

import streamlit as st

from src.clustering.geo_clusters import cluster_venues
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

        with st.spinner("Clustering venues into day groups…"):
            clusters = cluster_venues(matched, preferences["days"])

        st.success(
            f"Matched **{len(matched)}** venues → "
            f"grouped into **{len(clusters)}** day clusters."
        )

        for i, cluster in enumerate(clusters):
            with st.expander(f"Day {i + 1} — {len(cluster)} venues", expanded=False):
                for v in cluster:
                    st.write(
                        f"**{v['name']}** — {', '.join(v['categories'])} "
                        f"| score: {v.get('similarity_score', 0):.3f} "
                        f"| ({v['lat']:.4f}, {v['lon']:.4f})"
                    )

        with st.expander("Preference object (debug)", expanded=False):
            st.json(preferences)

        st.info("Next: LLM itinerary assembly → map display.")


if __name__ == "__main__":
    main()
