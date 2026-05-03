"""Multi-step onboarding preference form.

4 steps mirroring a mobile-app onboarding flow:
  0 — Where & When   (destination, duration, party size)
  1 — Travel Style   (budget, pace via st.pills)
  2 — Interests      (multi-select via st.pills)
  3 — Review & Go    (summary card, optional free-text, generate)
"""
from __future__ import annotations

import streamlit as st

# ── Constants ─────────────────────────────────────────────────────────────────

DESTINATIONS: list[str] = ["Goa, India"]

INTERESTS: list[str] = ["food", "history", "nature", "nightlife", "shopping", "art"]

INTEREST_LABELS: dict[str, str] = {
    "food":      "🍽️ Food & Dining",
    "history":   "🏛️ History",
    "nature":    "🌿 Nature",
    "nightlife": "🎉 Nightlife",
    "shopping":  "🛍️ Shopping",
    "art":       "🎨 Art & Museums",
}

BUDGET_OPTIONS: list[str] = ["budget", "mid-range", "luxury"]
BUDGET_LABELS: dict[str, str] = {
    "budget":    "💸 Budget",
    "mid-range": "💳 Mid-range",
    "luxury":    "💎 Luxury",
}
BUDGET_DESCS: dict[str, str] = {
    "budget":    "Street food, hostels & free attractions",
    "mid-range": "Restaurants, hotels & paid experiences",
    "luxury":    "Fine dining, resorts & private tours",
}

PACE_OPTIONS: list[str] = ["relaxed", "moderate", "packed"]
PACE_LABELS: dict[str, str] = {
    "relaxed":  "🧘 Relaxed",
    "moderate": "🚶 Moderate",
    "packed":   "⚡ Packed",
}
PACE_DESCS: dict[str, str] = {
    "relaxed":  "4-5 stops/day — unhurried, plenty of breathing room",
    "moderate": "5-6 stops/day — balanced mix of sights and downtime",
    "packed":   "6+ stops/day — maximise every hour",
}

# ── Session-state keys ────────────────────────────────────────────────────────

_STEP = "_form_step"
_DATA = "_form_data"

STEPS = [
    {"icon": "🌏", "title": "Where & When"},
    {"icon": "✨", "title": "Travel Style"},
    {"icon": "🎯", "title": "Interests"},
]


def _init() -> None:
    if _STEP not in st.session_state:
        st.session_state[_STEP] = 0
    if _DATA not in st.session_state:
        st.session_state[_DATA] = {
            "destination": DESTINATIONS[0],
            "days": 3, "party_size": 2,
            "budget_tier": "mid-range",
            "pace": "moderate",
            "interests": [],
            "free_text": "",
        }


# ── Public API ────────────────────────────────────────────────────────────────

# Widget keys that cache values across reruns — must be cleared when pre-filling
_WIDGET_KEYS = ("s0_days", "s0_party", "s1_budget", "s1_pace", "s2_interests", "s3_free_text")


def prefill_form(prefs: dict) -> None:
    """Load extracted preferences into form state and clear all widget caches.

    Called when the user clicks Edit on the summary screen.  Clearing the
    widget keys forces each st.slider / st.pills / st.number_input to
    re-read its value= argument from _DATA rather than its cached state.
    """
    st.session_state[_STEP] = 0
    st.session_state[_DATA] = {
        "destination": prefs.get("destination") or DESTINATIONS[0],
        "days":        int(prefs.get("days") or 3),
        "party_size":  int(prefs.get("party_size") or 2),
        "budget_tier": prefs.get("budget_tier") or "mid-range",
        "pace":        prefs.get("pace") or "moderate",
        "interests":   list(prefs.get("interests") or []),
        "free_text":   prefs.get("free_text") or "",
    }
    for key in _WIDGET_KEYS:
        st.session_state.pop(key, None)


def render_preference_form() -> dict | None:
    """Return preferences dict on final submit, else None."""
    _init()
    step = st.session_state[_STEP]
    data = st.session_state[_DATA]

    _render_progress(step)
    st.markdown("<div style='height:.75rem'></div>", unsafe_allow_html=True)

    if step == 0: return _step_where_when(data)
    if step == 1: return _step_style(data)
    if step == 2: return _step_interests(data)
    return None


# ── Progress indicator ────────────────────────────────────────────────────────

def _render_progress(current: int) -> None:
    items = ""
    for i, s in enumerate(STEPS):
        if i < current:
            cls, txt = "done", "✓"
        elif i == current:
            cls, txt = "active", str(i + 1)
        else:
            cls, txt = "future", str(i + 1)
        lbl_cls = "step-lbl-active" if i == current else ""
        connector = '<div class="step-conn"></div>' if i < len(STEPS) - 1 else ""
        items += (
            f'<div class="step-item">'
            f'  <div class="step-dot {cls}">{txt}</div>'
            f'  <div class="step-lbl {lbl_cls}">{s["title"]}</div>'
            f'</div>'
            f'{connector}'
        )
    st.markdown(
        f'<div class="onb-progress">{items}</div>',
        unsafe_allow_html=True,
    )


# ── Step 0 — Where & When ─────────────────────────────────────────────────────

def _step_where_when(data: dict) -> dict | None:
    _step_header("bi-geo-alt-fill", "Where & When?",
                 "Choose your destination and how long you want to stay.")

    # Destination — single option shown as a selected card
    st.markdown(
        '<div class="dest-card">'
        '  <span class="dest-flag">🇮🇳</span>'
        '  <div class="dest-body">'
        '    <div class="dest-name">Goa, India</div>'
        '    <div class="dest-tags">Beaches · Heritage · Nightlife</div>'
        '  </div>'
        '  <div class="dest-check"><i class="bi bi-check-lg"></i></div>'
        '</div>',
        unsafe_allow_html=True,
    )

    st.markdown("<div style='height:1rem'></div>", unsafe_allow_html=True)
    st.markdown('<p style="font-weight:700;margin-bottom:.25rem"><i class="bi bi-calendar3" style="color:#0EA5E9"></i> How many days?</p>', unsafe_allow_html=True)

    days = st.slider(
        "days_sl", label_visibility="collapsed",
        min_value=2, max_value=7,
        value=data.get("days", 3), key="s0_days",
    )

    st.markdown("<div style='height:1rem'></div>", unsafe_allow_html=True)
    st.markdown('<p style="font-weight:700;margin-bottom:.25rem"><i class="bi bi-people-fill" style="color:#0EA5E9"></i> How many travellers?</p>', unsafe_allow_html=True)
    party_size = st.number_input(
        "party_ni", label_visibility="collapsed",
        min_value=1, max_value=20,
        value=data.get("party_size", 2), step=1, key="s0_party",
    )

    st.markdown("<div style='height:1.5rem'></div>", unsafe_allow_html=True)
    if st.button("Next  →  Travel Style", type="primary",
                 use_container_width=True, key="next0"):
        data.update(destination=DESTINATIONS[0], days=int(days),
                    party_size=int(party_size))
        _save_data(data, next_step=1)
    return None


# ── Step 1 — Travel Style ─────────────────────────────────────────────────────

def _step_style(data: dict) -> dict | None:
    _step_header("bi-sliders", "Travel Style",
                 "Pick a budget and pace that suit you.")

    st.markdown('<p style="font-weight:700;margin-bottom:.25rem"><i class="bi bi-wallet2" style="color:#0EA5E9"></i> Budget</p>', unsafe_allow_html=True)
    budget = st.pills(
        "budget_p", label_visibility="collapsed",
        options=BUDGET_OPTIONS,
        format_func=lambda k: BUDGET_LABELS[k],
        selection_mode="single",
        default=data.get("budget_tier", "mid-range"),
        key="s1_budget",
    )
    if budget:
        st.caption(f"*{BUDGET_DESCS[budget]}*")

    st.markdown("<div style='height:1rem'></div>", unsafe_allow_html=True)
    st.markdown('<p style="font-weight:700;margin-bottom:.25rem"><i class="bi bi-lightning-charge" style="color:#0EA5E9"></i> Pace</p>', unsafe_allow_html=True)
    pace = st.pills(
        "pace_p", label_visibility="collapsed",
        options=PACE_OPTIONS,
        format_func=lambda k: PACE_LABELS[k],
        selection_mode="single",
        default=data.get("pace", "moderate"),
        key="s1_pace",
    )
    if pace:
        st.caption(f"*{PACE_DESCS[pace]}*")

    st.markdown("<div style='height:1.5rem'></div>", unsafe_allow_html=True)
    bc, nc = st.columns([1, 2])
    with bc:
        if st.button("←  Back", use_container_width=True, key="back1"):
            _save_data(data, next_step=0)
    with nc:
        if st.button("Next  →  Interests", type="primary",
                     use_container_width=True, key="next1"):
            if not budget:
                st.error("Please choose a budget tier.")
                return None
            if not pace:
                st.error("Please choose a pace.")
                return None
            data.update(budget_tier=budget, pace=pace)
            _save_data(data, next_step=2)
    return None


# ── Step 2 — Interests ────────────────────────────────────────────────────────

def _step_interests(data: dict) -> dict | None:
    _step_header("bi-heart-fill", "What Do You Love?",
                 "Pick every experience you want in your itinerary.")

    selected = st.pills(
        "interests_p", label_visibility="collapsed",
        options=INTERESTS,
        format_func=lambda k: INTEREST_LABELS[k],
        selection_mode="multi",
        default=data.get("interests", []),
        key="s2_interests",
    )

    if selected:
        n = len(selected)
        st.markdown(
            f'<p style="margin:.4rem 0 0;font-size:.85rem;'
            f'color:#0EA5E9;font-weight:600">'
            f'✓ {n} interest{"s" if n > 1 else ""} selected</p>',
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height:1.5rem'></div>", unsafe_allow_html=True)
    bc, nc = st.columns([1, 2])
    with bc:
        if st.button("←  Back", use_container_width=True, key="back2"):
            _save_data(data, next_step=1)
    with nc:
        if st.button("Save & Review  →", type="primary",
                     use_container_width=True, key="next2"):
            data["interests"] = list(selected or [])
            st.session_state[_DATA] = data
            st.session_state[_STEP] = 0
            # Return prefs so _page_form() can update _extracted_prefs
            # and navigate back to the summary page.
            return {
                "destination": data["destination"],
                "days":        data["days"],
                "party_size":  data["party_size"],
                "budget_tier": data["budget_tier"],
                "pace":        data["pace"],
                "interests":   data["interests"],
                "free_text":   data.get("free_text", ""),
            }
    return None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _step_header(icon: str, title: str, subtitle: str) -> None:
    # icon is a Bootstrap Icons class name, e.g. "bi-geo-alt-fill"
    st.markdown(
        f'<div class="step-hdr">'
        f'  <i class="bi {icon} step-hdr-icon"></i>'
        f'  <div>'
        f'    <h2 style="margin:0">{title}</h2>'
        f'    <p style="margin:.25rem 0 0;color:#64748B;font-size:.9rem">{subtitle}</p>'
        f'  </div>'
        f'</div>',
        unsafe_allow_html=True,
    )
    st.markdown("<div style='height:.75rem'></div>", unsafe_allow_html=True)


def _save_data(data: dict, next_step: int) -> None:
    st.session_state[_DATA]  = data
    st.session_state[_STEP]  = next_step
    st.rerun()


