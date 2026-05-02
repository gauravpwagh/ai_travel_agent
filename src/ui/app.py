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
from src.ui.forms import render_preference_form, render_sample_buttons
from src.ui.itinerary_view import render_itinerary
from src.validation.checks import validate_and_fix_itinerary

log = setup_logging()


# ── Global CSS ────────────────────────────────────────────────────────────────

_CSS = """
<style>
/* ── Base layout ── */
.stApp { background: #F1F5F9; }
.block-container {
    padding: 2rem 2.5rem 4rem;
    max-width: 1280px;
}

/* ── Typography ── */
h1 { font-size: 2.2rem !important; font-weight: 800 !important;
     color: #0F172A !important; letter-spacing: -0.5px; }
h2 { font-size: 1.4rem !important; font-weight: 700 !important;
     color: #0F172A !important; }
h3 { font-size: 1.1rem !important; font-weight: 600 !important;
     color: #1E293B !important; }
p, li { color: #334155; }

/* ── Hero header ── */
.travel-hero {
    background: linear-gradient(135deg, #0EA5E9 0%, #2563EB 50%, #4F46E5 100%);
    border-radius: 20px;
    padding: 2.5rem 2.5rem 2rem;
    margin-bottom: 1.5rem;
    color: white;
}
.travel-hero h1 { color: white !important; font-size: 2.4rem !important; margin: 0; }
.travel-hero p  { color: rgba(255,255,255,.85); font-size: 1.05rem; margin: .5rem 0 0; }

/* ── Sample preset buttons ── */
.preset-strip .stButton > button {
    border-radius: 20px;
    border: 1.5px solid #CBD5E1;
    background: white;
    color: #334155;
    font-size: .85rem;
    font-weight: 600;
    padding: .35rem 1rem;
    transition: all .15s ease;
}
.preset-strip .stButton > button:hover {
    border-color: #0EA5E9;
    color: #0EA5E9;
    box-shadow: 0 2px 8px rgba(14,165,233,.15);
    transform: translateY(-1px);
}

/* ── Form card ── */
.stForm {
    background: white !important;
    border-radius: 16px !important;
    padding: 1.75rem !important;
    box-shadow: 0 1px 3px rgba(0,0,0,.06), 0 4px 20px rgba(0,0,0,.05) !important;
    border: 1px solid #E2E8F0 !important;
}

/* ── Form submit button ── */
.stFormSubmitButton > button {
    background: linear-gradient(135deg, #0EA5E9, #2563EB) !important;
    color: white !important;
    border: none !important;
    border-radius: 12px !important;
    font-size: 1rem !important;
    font-weight: 700 !important;
    padding: .75rem !important;
    transition: all .2s ease !important;
    letter-spacing: .3px;
}
.stFormSubmitButton > button:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 6px 20px rgba(37,99,235,.4) !important;
}

/* ── Tabs ── */
.stTabs [data-baseweb="tab-list"] {
    gap: 4px;
    background: white;
    border-radius: 12px;
    padding: 4px;
    border: 1px solid #E2E8F0;
    box-shadow: 0 1px 3px rgba(0,0,0,.05);
    margin-bottom: .5rem;
}
.stTabs [data-baseweb="tab"] {
    border-radius: 8px;
    padding: 8px 20px;
    font-weight: 600;
    font-size: .9rem;
    color: #64748B;
    border: none !important;
    background: transparent;
    transition: all .15s ease;
}
.stTabs [aria-selected="true"] {
    background: linear-gradient(135deg, #0EA5E9, #2563EB) !important;
    color: white !important;
}
.stTabs [data-baseweb="tab-panel"] {
    padding-top: .75rem;
}

/* ── Bordered containers (venue cards) ── */
div[data-testid="stVerticalBlockBorderWrapper"] {
    border-radius: 14px !important;
    border: 1px solid #E2E8F0 !important;
    background: white !important;
    box-shadow: 0 1px 4px rgba(0,0,0,.05) !important;
    transition: box-shadow .2s ease;
    overflow: hidden;
}
div[data-testid="stVerticalBlockBorderWrapper"]:hover {
    box-shadow: 0 4px 16px rgba(0,0,0,.09) !important;
}

/* ── Feedback buttons ── */
.feedback-row .stButton > button {
    border-radius: 8px;
    font-size: .8rem;
    padding: .25rem .5rem;
    font-weight: 600;
    border: 1.5px solid #E2E8F0;
    background: #F8FAFC;
    color: #64748B;
    transition: all .15s ease;
}
.feedback-row .stButton > button:hover { border-color: #94A3B8; background: white; }

/* ── Transit / leg connector ── */
.leg-connector {
    display: flex; align-items: center; gap: 8px;
    margin: 2px 0 2px 4px;
    color: #94A3B8; font-size: .8rem;
}

/* ── Success / info banners ── */
.stSuccess, .stInfo, .stWarning, .stError { border-radius: 10px !important; }

/* ── Expander ── */
.stExpander { border-radius: 10px !important; border: 1px solid #E2E8F0 !important; }
details[open] > summary { font-weight: 600; }

/* ── Divider ── */
hr { border-color: #E2E8F0 !important; margin: 1.5rem 0 !important; }

/* ── Scrollbar polish ── */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: #CBD5E1; border-radius: 3px; }
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

    with st.container():
        st.markdown('<div class="preset-strip">', unsafe_allow_html=True)
        render_sample_buttons()
        st.markdown('</div>', unsafe_allow_html=True)

    st.divider()
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
