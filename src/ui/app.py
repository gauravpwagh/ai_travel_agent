"""Streamlit entrypoint for the AI Travel Itinerary Generator.

Session-state caching (Phase 2.4): the generated itinerary is stored in
st.session_state after the pipeline completes. Feedback button clicks trigger
a Streamlit rerun, but the form is not re-submitted so preferences is None —
the app reads from session state and re-renders without re-running the pipeline.
A new form submission clears the cache and runs the pipeline fresh.
"""
from __future__ import annotations

import streamlit as st
import streamlit.components.v1 as st_comp

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
from src.ui.forms import render_preference_form
from src.ui.itinerary_view import render_itinerary
from src.validation.checks import validate_and_fix_itinerary

log = setup_logging()


# ── Global CSS ────────────────────────────────────────────────────────────────

_CSS = """
<style>
/* ══════════════════════════════════════════════════════
   BASE
══════════════════════════════════════════════════════ */
.stApp { background: #F1F5F9; }
.block-container { padding: 2rem 2.5rem 4rem; max-width: 1280px; }

h1 { font-size: 2.2rem !important; font-weight: 800 !important;
     color: #0F172A !important; letter-spacing: -.5px; }
h2 { font-size: 1.35rem !important; font-weight: 700 !important;
     color: #0F172A !important; }
h3 { font-size: 1.05rem !important; font-weight: 600 !important;
     color: #1E293B !important; }
p, li { color: #334155; }
hr  { border-color: #E2E8F0 !important; margin: 1.25rem 0 !important; }
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-thumb { background: #CBD5E1; border-radius: 3px; }

/* ══════════════════════════════════════════════════════
   HERO HEADER
══════════════════════════════════════════════════════ */
.travel-hero {
    background: linear-gradient(135deg, #0EA5E9 0%, #2563EB 55%, #4F46E5 100%);
    border-radius: 20px;
    padding: 2.25rem 2.5rem 2rem;
    margin-bottom: 1.25rem;
}
.travel-hero h1 { color: white !important; font-size: 2.3rem !important; margin: 0; }
.travel-hero p  { color: rgba(255,255,255,.85); font-size: 1rem; margin: .4rem 0 0; }

/* ══════════════════════════════════════════════════════
   ONBOARDING — PROGRESS BAR
══════════════════════════════════════════════════════ */
.onb-progress {
    display: flex; align-items: flex-start; justify-content: center;
    gap: 0; padding: 1.25rem 1rem .9rem;
    background: white; border-radius: 16px;
    border: 1px solid #E2E8F0;
    box-shadow: 0 1px 4px rgba(0,0,0,.05);
}
.step-item  { display: flex; flex-direction: column; align-items: center; gap: 6px; }
.step-conn  { width: 56px; height: 2px; background: #E2E8F0;
              margin-top: 17px; flex-shrink: 0; }
.step-dot {
    width: 34px; height: 34px; border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-weight: 700; font-size: 13px;
    border: 2px solid #E2E8F0; background: #F8FAFC; color: #94A3B8;
}
.step-dot.done   { background: #D1FAE5; border-color: #059669; color: #059669; }
.step-dot.active {
    background: linear-gradient(135deg, #0EA5E9, #2563EB);
    border-color: transparent; color: white;
    box-shadow: 0 3px 10px rgba(14,165,233,.4);
}
.step-lbl        { font-size: .71rem; font-weight: 500; color: #94A3B8;
                   white-space: nowrap; }
.step-lbl-active { color: #0EA5E9 !important; font-weight: 700 !important; }


/* ══════════════════════════════════════════════════════
   ONBOARDING — STEP HEADER
══════════════════════════════════════════════════════ */
.step-hdr {
    display: flex; align-items: center; gap: 1rem; margin-bottom: 1.25rem;
}
.step-hdr-icon { font-size: 2.4rem; line-height: 1; }

/* ══════════════════════════════════════════════════════
   ONBOARDING — DESTINATION CARD
══════════════════════════════════════════════════════ */
.dest-card {
    display: flex; align-items: center; gap: 1rem;
    padding: 1rem 1.25rem;
    background: linear-gradient(135deg, #EFF6FF 0%, #F0FDF4 100%);
    border: 2px solid #0EA5E9; border-radius: 14px;
}
.dest-flag { font-size: 2rem; }
.dest-name { font-weight: 700; font-size: 1rem; color: #0F172A; }
.dest-tags { font-size: .8rem; color: #64748B; margin-top: 2px; }
.dest-check {
    margin-left: auto; background: #0EA5E9; color: white;
    width: 24px; height: 24px; border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-size: .75rem; font-weight: 700;
}

/* ══════════════════════════════════════════════════════
   ONBOARDING — DAY PIPS
══════════════════════════════════════════════════════ */
.day-pips    { display: flex; gap: 8px; margin-top: .5rem; }
.day-pip {
    width: 34px; height: 34px; border-radius: 50%;
    background: #F1F5F9; border: 2px solid #E2E8F0;
    display: flex; align-items: center; justify-content: center;
    font-weight: 600; font-size: .8rem; color: #94A3B8;
}
.day-pip-on {
    background: linear-gradient(135deg, #0EA5E9, #2563EB);
    border-color: transparent; color: white;
    box-shadow: 0 3px 10px rgba(14,165,233,.4);
}

/* ══════════════════════════════════════════════════════
   ONBOARDING — SUMMARY CARD (Review step)
══════════════════════════════════════════════════════ */
.sum-card {
    background: #F8FAFC; border: 1px solid #E2E8F0;
    border-radius: 14px; padding: .9rem 1.25rem;
    display: flex; flex-direction: column; gap: .55rem;
}
.sum-row { display: flex; align-items: flex-start; gap: .75rem; }
.sum-key { font-size: .82rem; color: #64748B; font-weight: 600; min-width: 120px; }
.sum-val { font-size: .88rem; color: #0F172A; font-weight: 500; }

/* ══════════════════════════════════════════════════════
   st.pills — larger, more app-like
══════════════════════════════════════════════════════ */
div[data-testid="stPills"] { gap: 8px !important; flex-wrap: wrap !important; }
div[data-testid="stPills"] button {
    border-radius: 22px !important; padding: .45rem 1.15rem !important;
    font-size: .88rem !important; font-weight: 600 !important;
    border: 2px solid #E2E8F0 !important;
    background: white !important; color: #475569 !important;
    transition: all .15s ease !important;
}
div[data-testid="stPills"] button[aria-selected="true"] {
    background: linear-gradient(135deg, #0EA5E9, #2563EB) !important;
    border-color: transparent !important; color: white !important;
    box-shadow: 0 3px 10px rgba(14,165,233,.35) !important;
}
div[data-testid="stPills"] button:hover:not([aria-selected="true"]) {
    border-color: #94A3B8 !important; color: #1E293B !important;
}

/* ══════════════════════════════════════════════════════
   NAVIGATION BUTTONS (Back / Next)
══════════════════════════════════════════════════════ */
.stButton > button {
    border-radius: 10px; font-weight: 600;
    border: 1.5px solid #E2E8F0; transition: all .15s ease;
}
.stButton > button[kind="primary"],
.stButton > button[data-testid="baseButton-primary"] {
    background: linear-gradient(135deg, #0EA5E9, #2563EB) !important;
    border: none !important; color: white !important;
    font-size: .95rem !important;
}
.stButton > button[kind="primary"]:hover {
    transform: translateY(-1px) !important;
    box-shadow: 0 5px 18px rgba(37,99,235,.38) !important;
}

/* ══════════════════════════════════════════════════════
   BORDERED CONTAINERS (venue cards)
══════════════════════════════════════════════════════ */
div[data-testid="stVerticalBlockBorderWrapper"] {
    border-radius: 14px !important; border: 1px solid #E2E8F0 !important;
    background: white !important;
    box-shadow: 0 1px 4px rgba(0,0,0,.05) !important;
    transition: box-shadow .2s ease;
    overflow: hidden;
}
div[data-testid="stVerticalBlockBorderWrapper"]:hover {
    box-shadow: 0 4px 16px rgba(0,0,0,.09) !important;
}

/* ══════════════════════════════════════════════════════
   ITINERARY TABS
══════════════════════════════════════════════════════ */
.stTabs [data-baseweb="tab-list"] {
    gap: 4px; background: white; border-radius: 12px;
    padding: 4px; border: 1px solid #E2E8F0;
    box-shadow: 0 1px 3px rgba(0,0,0,.05); margin-bottom: .5rem;
}
.stTabs [data-baseweb="tab"] {
    border-radius: 8px; padding: 8px 20px;
    font-weight: 600; font-size: .88rem; color: #64748B;
    border: none !important; background: transparent; transition: all .15s;
}
.stTabs [aria-selected="true"] {
    background: linear-gradient(135deg, #0EA5E9, #2563EB) !important;
    color: white !important;
}
.stTabs [data-baseweb="tab-panel"] { padding-top: .75rem; }

/* ══════════════════════════════════════════════════════
   VENUE CARDS
══════════════════════════════════════════════════════ */
.feedback-row .stButton > button {
    border-radius: 8px; font-size: .8rem; font-weight: 600;
    border: 1.5px solid #E2E8F0; background: #F8FAFC; color: #64748B;
}
.feedback-row .stButton > button:hover { border-color: #94A3B8; background: white; }
.leg-connector {
    display: flex; align-items: center; gap: 8px;
    margin: 2px 0 2px 4px; color: #94A3B8; font-size: .8rem;
}

/* ══════════════════════════════════════════════════════
   MISC
══════════════════════════════════════════════════════ */
.stSuccess, .stInfo, .stWarning, .stError { border-radius: 10px !important; }
.stExpander { border-radius: 10px !important; border: 1px solid #E2E8F0 !important; }
details[open] > summary { font-weight: 600; }
</style>
"""


def _inject_css() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)


def _scroll_to_top() -> None:
    """Inject JS to scroll the Streamlit page back to the top after swap rerun."""
    st_comp.html(
        """<script>
        (function() {
            var attempts = 0;
            function tryScroll() {
                var frame = window.parent.document.querySelector('[data-testid="stAppViewContainer"]')
                         || window.parent.document.querySelector('.main')
                         || window.parent.document.body;
                if (frame) { frame.scrollTop = 0; }
                window.parent.scrollTo({ top: 0, behavior: 'smooth' });
                if (attempts++ < 5) setTimeout(tryScroll, 80);
            }
            tryScroll();
        })();
        </script>""",
        height=0,
        scrolling=False,
    )


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    st.set_page_config(
        page_title="AI Travel Planner",
        page_icon="✈️",
        layout="wide",
        initial_sidebar_state="collapsed",
    )

    _inject_css()
    init_db()

    # Hero header
    st.markdown(
        """<div class="travel-hero">
            <h1>✈️ AI Travel Planner</h1>
            <p>Tell us your preferences and get a day-by-day itinerary with real venues,
               maps, and travel times — in under 2 minutes.</p>
        </div>""",
        unsafe_allow_html=True,
    )

    # ── Multi-step onboarding form (centred via column gutter) ───────────────
    _, form_col, _ = st.columns([1, 6, 1])
    with form_col:
        preferences = render_preference_form()

    # ── New form submission → clear cache, run pipeline ───────────────────────
    if preferences is not None:
        clear_itinerary_state()
        _run_pipeline(preferences)

    # ── Scroll-to-top after swap ──────────────────────────────────────────────
    if st.session_state.pop("_scroll_top", False):
        _scroll_to_top()

    # ── Render from session state (new generation OR feedback rerun) ──────────
    state = load_itinerary_state()
    if state:
        dest = state["preferences"]["destination"]
        days = state["preferences"]["days"]
        st.markdown(
            f"""<div style="background:white;border-radius:14px;padding:1rem 1.5rem;
                margin:1rem 0 .5rem;border:1px solid #E2E8F0;
                box-shadow:0 1px 4px rgba(0,0,0,.05)">
                <span style="font-size:1.2rem;font-weight:700;color:#0F172A">
                ✅ Your {days}-day itinerary for <span style="color:#0EA5E9">{dest}</span> is ready!</span>
            </div>""",
            unsafe_allow_html=True,
        )
        render_itinerary(
            itinerary=state["itinerary"],
            clusters=state["clusters"],
            issues=state["issues"],
            itinerary_id=state["itinerary_id"],
            venue_lookup=state["venue_lookup"],
        )
        with st.expander("🔧 Debug — preferences", expanded=False):
            st.json(state["preferences"])


# ── Pipeline ──────────────────────────────────────────────────────────────────

def _run_pipeline(preferences: dict) -> None:
    """Execute all generation steps and store the result in session state."""
    destination = preferences["destination"]

    venues = get_venues_by_destination(destination)
    if not venues:
        st.warning(
            f"No cached venues for **{destination}**. "
            'Run `python -m src.ingestion.overpass --destination "Goa, India"` first.'
        )
        return

    with st.spinner("🔍 Matching venues to your preferences…"):
        embed_and_cache(destination)
        venues = get_venues_by_destination(destination)
        matched = match_venues(venues, preferences)

    with st.spinner("📍 Grouping venues into days…"):
        clusters = cluster_venues(matched, preferences["days"])

    with st.spinner(
        f"✨ Crafting your {preferences['days']}-day itinerary… (one AI call per day)"
    ):
        try:
            itinerary = build_itinerary(clusters, preferences)
        except Exception as exc:
            st.error(f"Itinerary generation failed: {exc}")
            log.exception("build_itinerary failed")
            return

    venue_lookup = {v["osm_id"]: v for c in clusters for v in c}

    with st.spinner("🗺️ Estimating travel times between venues…"):
        annotate_itinerary_travel_times(itinerary, venue_lookup)

    with st.spinner("🛡️ Validating itinerary…"):
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
