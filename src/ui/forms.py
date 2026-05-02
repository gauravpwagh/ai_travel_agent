"""Multi-step onboarding preference form.

4 steps mirroring a mobile-app onboarding flow:
  0 — Where & When   (destination, duration, party size)
  1 — Travel Style   (budget, pace via st.pills)
  2 — Interests      (multi-select via st.pills)
  3 — Review & Go    (summary card, optional free-text, generate)

Preset cards sit above the steps.  Clicking one pre-fills all step state
and jumps straight to the Review step with a "✓ Selected" visual.
"""
from __future__ import annotations

import streamlit as st

from src.generation.extractor import extract_preferences, extraction_summary, merge_preferences

# ── Constants ─────────────────────────────────────────────────────────────────

DESTINATIONS: list[str] = ["Goa, India"]

INTERESTS: list[str] = ["food", "history", "nature", "nightlife", "shopping", "art", "beaches"]

INTEREST_LABELS: dict[str, str] = {
    "food":      "🍽️ Food & Dining",
    "history":   "🏛️ History",
    "nature":    "🌿 Nature",
    "nightlife": "🎉 Nightlife",
    "shopping":  "🛍️ Shopping",
    "art":       "🎨 Art & Museums",
    "beaches":   "🏖️ Beaches",
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

SAMPLE_INPUTS: dict[str, dict] = {
    "🍽️ Foodie Weekend": {
        "destination": "Goa, India",
        "days": 3, "party_size": 2,
        "budget_tier": "mid-range",
        "interests": ["food", "beaches", "nightlife"],
        "pace": "relaxed",
    },
    "🏛️ Culture Explorer": {
        "destination": "Goa, India",
        "days": 5, "party_size": 1,
        "budget_tier": "budget",
        "interests": ["history", "art", "nature"],
        "pace": "moderate",
    },
    "👨‍👩‍👧‍👦 Family Vacation": {
        "destination": "Goa, India",
        "days": 4, "party_size": 4,
        "budget_tier": "mid-range",
        "interests": ["beaches", "nature", "food", "shopping"],
        "pace": "relaxed",
    },
}

# ── Session-state keys ────────────────────────────────────────────────────────

_STEP  = "_form_step"
_DATA  = "_form_data"
_PKEY  = "_selected_preset"

STEPS = [
    {"icon": "🌏", "title": "Where & When"},
    {"icon": "✨", "title": "Travel Style"},
    {"icon": "🎯", "title": "Interests"},
    {"icon": "✍️",  "title": "Review & Go"},
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
    if _PKEY not in st.session_state:
        st.session_state[_PKEY] = None


# ── Public API ────────────────────────────────────────────────────────────────

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
    if step == 3: return _step_review(data)
    return None


def render_sample_buttons() -> None:
    """Preset cards — selected one shows a ✓ Selected primary button."""
    selected = st.session_state.get(_PKEY)
    st.markdown(
        "<p style='margin:0 0 .6rem;font-size:.75rem;font-weight:700;"
        "text-transform:uppercase;letter-spacing:.8px;color:#94A3B8'>Quick Start</p>",
        unsafe_allow_html=True,
    )
    cols = st.columns(len(SAMPLE_INPUTS))
    for col, (label, preset) in zip(cols, SAMPLE_INPUTS.items()):
        with col:
            is_sel = selected == label
            with st.container(border=True):
                _preset_card_body(label, preset, is_sel)
                btn_label = "✓  Selected" if is_sel else "Use this  →"
                btn_type  = "primary" if is_sel else "secondary"
                if st.button(btn_label, key=f"preset_{label}",
                             use_container_width=True, type=btn_type):
                    _load_preset(label, preset)


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
    _step_header("🌏", "Where & When?",
                 "Choose your destination and how long you want to stay.")

    # Destination — single option shown as a selected card
    st.markdown(
        '<div class="dest-card">'
        '  <span class="dest-flag">🇮🇳</span>'
        '  <div class="dest-body">'
        '    <div class="dest-name">Goa, India</div>'
        '    <div class="dest-tags">Beaches · Heritage · Nightlife</div>'
        '  </div>'
        '  <div class="dest-check">✓</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    st.markdown("<div style='height:1rem'></div>", unsafe_allow_html=True)
    st.markdown("**📅 How many days?**")

    days = st.slider(
        "days_sl", label_visibility="collapsed",
        min_value=2, max_value=7,
        value=data.get("days", 3), key="s0_days",
    )
    # Day pip row
    pips = "".join(
        f'<div class="day-pip {"day-pip-on" if d == days else ""}">{d}</div>'
        for d in range(2, 8)
    )
    st.markdown(f'<div class="day-pips">{pips}</div>', unsafe_allow_html=True)

    st.markdown("<div style='height:1rem'></div>", unsafe_allow_html=True)
    st.markdown("**👥 How many travellers?**")
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
    _step_header("✨", "Travel Style",
                 "Pick a budget and pace that suit you.")

    st.markdown("**💰 Budget**")
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
    st.markdown("**⚡ Pace**")
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
    _step_header("🎯", "What Do You Love?",
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
        if st.button("Next  →  Review", type="primary",
                     use_container_width=True, key="next2"):
            data["interests"] = list(selected or [])
            _save_data(data, next_step=3)
    return None


# ── Step 3 — Review & Generate ────────────────────────────────────────────────

def _step_review(data: dict) -> dict | None:
    _step_header("✍️", "Review & Generate",
                 "Check your choices and add any extra detail (optional).")

    # Summary card
    interests_str = "  ·  ".join(INTEREST_LABELS.get(i, i) for i in data.get("interests", []))
    rows = [
        ("🌏 Destination", data.get("destination", "")),
        ("📅 Duration",
         f"{data.get('days', 0)} days  ·  "
         f"{data.get('party_size', 1)} traveller{'s' if data.get('party_size', 1) > 1 else ''}"),
        ("💰 Budget", BUDGET_LABELS.get(data.get("budget_tier", ""), "")),
        ("⚡ Pace",   PACE_LABELS.get(data.get("pace", ""), "")),
    ]
    if data.get("interests"):
        rows.append(("🎯 Interests", interests_str))

    rows_html = "".join(
        f'<div class="sum-row">'
        f'  <span class="sum-key">{k}</span>'
        f'  <span class="sum-val">{v}</span>'
        f'</div>'
        for k, v in rows
    )
    st.markdown(f'<div class="sum-card">{rows_html}</div>', unsafe_allow_html=True)

    st.markdown("<div style='height:.75rem'></div>", unsafe_allow_html=True)

    # Optional free text
    st.markdown(
        "<p style='font-weight:600;color:#1E293B;margin-bottom:.25rem'>"
        "Anything to add?  "
        "<span style='color:#94A3B8;font-weight:400;font-size:.88rem'>(optional — AI reads this for extra preferences)</span>"
        "</p>",
        unsafe_allow_html=True,
    )
    free_text = st.text_area(
        "free_text_r", label_visibility="collapsed",
        placeholder=(
            "e.g. 'We love street art and sunset spots. "
            "Skip museums please — prefer outdoor experiences.'"
        ),
        height=90,
        value=data.get("free_text", ""),
        key="s3_free_text",
    )

    st.markdown("<div style='height:1rem'></div>", unsafe_allow_html=True)

    bc, gc = st.columns([1, 2])
    with bc:
        if st.button("←  Edit", use_container_width=True, key="back3"):
            _save_data(data, next_step=2)
    with gc:
        generate = st.button(
            "✈️  Generate My Itinerary",
            type="primary", use_container_width=True, key="gen_btn",
        )

    if not generate:
        return None

    # ── Validate ──────────────────────────────────────────────────────────────
    data["free_text"] = free_text.strip()

    prefs: dict = {
        "destination": data["destination"],
        "days":        data["days"],
        "party_size":  data["party_size"],
        "budget_tier": data["budget_tier"],
        "interests":   list(data.get("interests", [])),
        "pace":        data["pace"],
    }

    # Free-text extraction + merge
    if data.get("free_text"):
        with st.spinner("✨ Reading your description…"):
            extracted = extract_preferences(data["free_text"])
        prefs = merge_preferences(prefs, extracted)
        summary = extraction_summary(extracted)
        if summary:
            added = prefs.get("_extracted_interests", [])
            badge = f"  ·  added: **{', '.join(added)}**" if added else ""
            st.info(f"✨ {summary}{badge}")

    if not prefs.get("interests"):
        st.error("Please select at least one interest, or describe your trip above.")
        return None

    prefs.pop("_extracted_interests", None)

    # Reset form to step 0 so it's clean when shown above the new itinerary
    st.session_state[_STEP] = 0
    st.session_state[_PKEY] = None
    return prefs


# ── Helpers ───────────────────────────────────────────────────────────────────

def _step_header(icon: str, title: str, subtitle: str) -> None:
    st.markdown(
        f'<div class="step-hdr">'
        f'  <span class="step-hdr-icon">{icon}</span>'
        f'  <div>'
        f'    <h2 style="margin:0">{title}</h2>'
        f'    <p style="margin:.25rem 0 0;color:#64748B;font-size:.9rem">{subtitle}</p>'
        f'  </div>'
        f'</div>',
        unsafe_allow_html=True,
    )
    st.markdown("<div style='height:.75rem'></div>", unsafe_allow_html=True)


def _preset_card_body(label: str, preset: dict, selected: bool) -> None:
    title_color = "#0EA5E9" if selected else "#0F172A"
    budget_lbl  = BUDGET_LABELS.get(preset["budget_tier"], preset["budget_tier"])
    pace_lbl    = PACE_LABELS.get(preset["pace"], preset["pace"])
    ints        = "  ·  ".join(INTEREST_LABELS.get(i, i) for i in preset["interests"][:3])
    st.markdown(
        f'<p style="font-weight:700;font-size:.95rem;margin:0 0 .2rem;color:{title_color}">'
        f'{label}</p>',
        unsafe_allow_html=True,
    )
    st.caption(f"{preset['days']} days  ·  {budget_lbl}  ·  {pace_lbl}")
    st.caption(f"🎯 {ints}")


def _save_data(data: dict, next_step: int) -> None:
    st.session_state[_DATA]  = data
    st.session_state[_STEP]  = next_step
    st.rerun()


def _load_preset(label: str, preset: dict) -> None:
    """Fill all form state from preset and jump to Review step."""
    st.session_state[_DATA] = {
        "destination": preset["destination"],
        "days":        preset["days"],
        "party_size":  preset["party_size"],
        "budget_tier": preset["budget_tier"],
        "pace":        preset["pace"],
        "interests":   list(preset["interests"]),
        "free_text":   "",
    }
    st.session_state[_PKEY] = label
    st.session_state[_STEP] = 3
    # Sync widget state so pills/sliders show preset values if user goes back
    st.session_state["s0_days"]       = preset["days"]
    st.session_state["s0_party"]      = preset["party_size"]
    st.session_state["s1_budget"]     = preset["budget_tier"]
    st.session_state["s1_pace"]       = preset["pace"]
    st.session_state["s2_interests"]  = list(preset["interests"])
    st.rerun()
