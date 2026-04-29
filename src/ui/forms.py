"""Streamlit preference input form.

Returns a normalized preference dict on submission. Free-text input is Phase 2.
"""
from __future__ import annotations

import streamlit as st

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

    st.header("Plan Your Trip")

    with st.form("preference_form", clear_on_submit=False):
        col1, col2 = st.columns(2)

        with col1:
            destination = st.selectbox(
                "Destination",
                options=DESTINATIONS,
                index=_form_default("destination", DESTINATIONS, DESTINATIONS[0]),
                help="More cities coming soon.",
            )

            days = st.slider(
                "Trip Duration (days)",
                min_value=2,
                max_value=7,
                value=_form_default("days", None, 3),
            )

            party_size = st.number_input(
                "Number of Travellers",
                min_value=1,
                max_value=20,
                value=_form_default("party_size", None, 2),
                step=1,
            )

        with col2:
            budget_tier = st.radio(
                "Budget",
                options=BUDGET_OPTIONS,
                format_func=lambda k: BUDGET_LABELS[k],
                index=_form_default("budget_tier", BUDGET_OPTIONS, "mid-range"),
            )

            pace = st.radio(
                "Pace",
                options=PACE_OPTIONS,
                format_func=lambda k: PACE_LABELS[k],
                index=_form_default("pace", PACE_OPTIONS, "moderate"),
            )

        st.markdown("**Interests** *(pick at least one)*")
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

        submitted = st.form_submit_button(
            "Generate Itinerary ✈️", use_container_width=True, type="primary"
        )

    # Clear preset after form renders so it doesn't sticky
    if "_preset" in st.session_state:
        del st.session_state["_preset"]

    if submitted:
        if not selected_interests:
            st.error("Please select at least one interest.")
            return None

        prefs: dict = {
            "destination": destination,
            "days": int(days),
            "party_size": int(party_size),
            "budget_tier": budget_tier,
            "interests": selected_interests,
            "pace": pace,
        }
        return prefs

    return None


def render_sample_buttons() -> None:
    """Render preset buttons above the form to pre-populate it."""
    st.markdown("##### Quick start — try a preset:")
    cols = st.columns(len(SAMPLE_INPUTS))
    for col, (label, preset) in zip(cols, SAMPLE_INPUTS.items()):
        if col.button(label, use_container_width=True):
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
