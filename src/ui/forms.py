"""Streamlit preference input form.

Phase 2.3: includes a free-text textarea whose contents are sent to the
LLM extractor after submission. Extracted preferences are merged with
the form values (form overrides on conflict; interests are unioned).
"""
from __future__ import annotations

import streamlit as st

from src.generation.extractor import extract_preferences, extraction_summary, merge_preferences

# ── Constants ────────────────────────────────────────────────────────────────

DESTINATIONS: list[str] = [
    "Goa, India",
]

INTERESTS: list[str] = [
    "food",
    "history",
    "nature",
    "nightlife",
    "shopping",
    "art",
    "beaches",
]

INTEREST_LABELS: dict[str, str] = {
    "food": "🍽️ Food & Dining",
    "history": "🏛️ History & Culture",
    "nature": "🌿 Nature & Parks",
    "nightlife": "🎉 Nightlife",
    "shopping": "🛍️ Shopping",
    "art": "🎨 Art & Museums",
    "beaches": "🏖️ Beaches",
}

BUDGET_OPTIONS: list[str] = ["budget", "mid-range", "luxury"]

BUDGET_LABELS: dict[str, str] = {
    "budget": "💸 Budget (street food, hostels)",
    "mid-range": "💳 Mid-range (restaurants, hotels)",
    "luxury": "💎 Luxury (fine dining, resorts)",
}

PACE_OPTIONS: list[str] = ["relaxed", "moderate", "packed"]

PACE_LABELS: dict[str, str] = {
    "relaxed": "🧘 Relaxed (4-5 venues/day)",
    "moderate": "🚶 Moderate (5-6 venues/day)",
    "packed": "⚡ Packed (6+ venues/day)",
}

# Sample presets for the "Try sample input" button
SAMPLE_INPUTS: dict[str, dict] = {
    "Foodie Weekend": {
        "destination": "Goa, India",
        "days": 3,
        "party_size": 2,
        "budget_tier": "mid-range",
        "interests": ["food", "beaches", "nightlife"],
        "pace": "relaxed",
    },
    "Culture Explorer": {
        "destination": "Goa, India",
        "days": 5,
        "party_size": 1,
        "budget_tier": "budget",
        "interests": ["history", "art", "nature"],
        "pace": "moderate",
    },
    "Family Vacation": {
        "destination": "Goa, India",
        "days": 4,
        "party_size": 4,
        "budget_tier": "mid-range",
        "interests": ["beaches", "nature", "food", "shopping"],
        "pace": "relaxed",
    },
}


# ── Form renderer ─────────────────────────────────────────────────────────────

def render_preference_form() -> dict | None:
    """Render the preference input form.

    Returns a normalized preference dict when the user submits, else None.
    """
    _apply_preset_if_requested()

    st.markdown(
        "<h2 style='margin-bottom:.25rem'>Plan Your Trip</h2>",
        unsafe_allow_html=True,
    )

    with st.form("preference_form", clear_on_submit=False):
        # ── Row 1: destination / duration / party size ────────────────────
        c1, c2, c3 = st.columns([2, 2, 1])
        with c1:
            destination = st.selectbox(
                "🌏 Destination",
                options=DESTINATIONS,
                index=_form_default("destination", DESTINATIONS, DESTINATIONS[0]),
                help="More cities coming soon.",
            )
        with c2:
            days = st.slider(
                "📅 Trip Duration (days)",
                min_value=2,
                max_value=7,
                value=_form_default("days", None, 3),
            )
        with c3:
            party_size = st.number_input(
                "👥 Travellers",
                min_value=1,
                max_value=20,
                value=_form_default("party_size", None, 2),
                step=1,
            )

        st.markdown("<div style='height:.25rem'></div>", unsafe_allow_html=True)

        # ── Row 2: budget / pace ──────────────────────────────────────────
        col_b, col_p = st.columns(2)
        with col_b:
            budget_tier = st.radio(
                "💰 Budget",
                options=BUDGET_OPTIONS,
                format_func=lambda k: BUDGET_LABELS[k],
                index=_form_default("budget_tier", BUDGET_OPTIONS, "mid-range"),
                horizontal=False,
            )
        with col_p:
            pace = st.radio(
                "⚡ Pace",
                options=PACE_OPTIONS,
                format_func=lambda k: PACE_LABELS[k],
                index=_form_default("pace", PACE_OPTIONS, "moderate"),
                horizontal=False,
            )

        st.markdown("<div style='height:.25rem'></div>", unsafe_allow_html=True)

        # ── Free-text ─────────────────────────────────────────────────────
        st.markdown(
            "<p style='margin-bottom:.3rem;font-weight:600;color:#1E293B'>"
            "✍️ Describe your ideal trip <span style='font-weight:400;color:#94A3B8'>(optional — AI will extract preferences)</span></p>",
            unsafe_allow_html=True,
        )
        free_text = st.text_area(
            label="free_text",
            label_visibility="collapsed",
            placeholder=(
                "e.g. 'I want a relaxed beach holiday with great seafood. "
                "We\'re a couple on a mid-range budget — no rushing around.'"
            ),
            height=85,
            key="free_text_input",
        )

        st.markdown("<div style='height:.25rem'></div>", unsafe_allow_html=True)

        # ── Interests ─────────────────────────────────────────────────────
        st.markdown(
            "<p style='margin-bottom:.3rem;font-weight:600;color:#1E293B'>"
            "🎯 Interests <span style='font-weight:400;color:#94A3B8'>(pick at least one)</span></p>",
            unsafe_allow_html=True,
        )
        interest_cols = st.columns(4)
        selected_interests: list[str] = []
        preset_interests: list[str] = st.session_state.get("_preset", {}).get(
            "interests", []
        )
        for i, interest in enumerate(INTERESTS):
            default_checked = interest in preset_interests if preset_interests else False
            if interest_cols[i % 4].checkbox(
                INTEREST_LABELS[interest],
                value=default_checked,
                key=f"interest_{interest}",
            ):
                selected_interests.append(interest)

        st.markdown("<div style='height:.5rem'></div>", unsafe_allow_html=True)

        submitted = st.form_submit_button(
            "✈️  Generate My Itinerary", use_container_width=True, type="primary"
        )

    # Clear preset after form renders so it doesn't sticky
    if "_preset" in st.session_state:
        del st.session_state["_preset"]

    if submitted:
        form_prefs: dict = {
            "destination": destination,
            "days": int(days),
            "party_size": int(party_size),
            "budget_tier": budget_tier,
            "interests": selected_interests,
            "pace": pace,
        }

        # ── Free-text extraction + merge ──────────────────────────────────
        if free_text.strip():
            with st.spinner("✨ Extracting preferences from your description…"):
                extracted = extract_preferences(free_text.strip())
            prefs = merge_preferences(form_prefs, extracted)

            summary = extraction_summary(extracted)
            if summary:
                added = prefs.get("_extracted_interests", [])
                badge = f" · added interests: **{', '.join(added)}**" if added else ""
                st.info(f"✨ Extracted from your text — {summary}{badge}")
        else:
            extracted = {}
            prefs = form_prefs

        # Validation: at least one interest (from form or extraction)
        if not prefs.get("interests"):
            st.error("Please select at least one interest, or describe your trip above.")
            return None

        # Remove internal keys before returning
        prefs.pop("_extracted_interests", None)
        return prefs

    return None


def render_sample_buttons() -> None:
    """Render preset buttons above the form to pre-populate it."""
    st.markdown(
        "<p style='margin-bottom:.4rem;font-size:.85rem;color:#94A3B8;font-weight:600;"
        "text-transform:uppercase;letter-spacing:.5px'>Quick start</p>",
        unsafe_allow_html=True,
    )
    cols = st.columns(len(SAMPLE_INPUTS))
    for col, (label, preset) in zip(cols, SAMPLE_INPUTS.items()):
        if col.button(f"✦ {label}", use_container_width=True):
            st.session_state["_preset"] = preset
            st.rerun()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _apply_preset_if_requested() -> None:
    """Copy preset values into session state keys used as widget defaults."""
    preset = st.session_state.get("_preset")
    if not preset:
        return
    # Store scalar defaults so _form_default() picks them up
    for key in ("destination", "days", "party_size", "budget_tier", "pace"):
        if key in preset:
            st.session_state[f"_default_{key}"] = preset[key]
    # Interests are handled inline in the form


def _form_default(key: str, options: list | None, fallback):
    """Return either a preset default or the fallback value.

    For selectbox/radio, returns the index in options.
    For slider/number_input, returns the raw value.
    """
    stored = st.session_state.get(f"_default_{key}")
    value = stored if stored is not None else fallback
    # Clear after reading so it only applies once
    if stored is not None:
        del st.session_state[f"_default_{key}"]
    if options is not None:
        try:
            return options.index(value)
        except ValueError:
            return 0
    return value
