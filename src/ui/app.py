"""Streamlit entrypoint for the AI Travel Itinerary Generator."""
from __future__ import annotations

import json

import streamlit as st

from src.config import setup_logging
from src.db import init_db
from src.ui.forms import render_preference_form, render_sample_buttons

log = setup_logging()


def main() -> None:
    st.set_page_config(
        page_title="AI Travel Planner",
        page_icon="✈️",
        layout="wide",
        initial_sidebar_state="collapsed",
    )

    # Ensure DB exists (idempotent)
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

    # ── Post-submission placeholder ───────────────────────────────────────────
    if preferences is not None:
        log.info("Preferences submitted: %s", preferences)
        st.success("Preferences received! Itinerary generation coming in Phase 1.4.")

        with st.expander("Normalized preference object (debug)", expanded=True):
            st.json(preferences)

        st.info(
            "Pipeline stages remaining: venue matching → clustering → "
            "LLM assembly → map display."
        )


if __name__ == "__main__":
    main()
