"""Streamlit entrypoint — 3-page flow.

  Page 1 (welcome)   — landing hero + feature cards + "Let's Go" CTA
  Page 2 (form)      — multi-step onboarding form → Generate
  Page 3 (itinerary) — day tabs, map + venue cards, feedback buttons

Navigation is driven by st.session_state["_page"].
The generated itinerary is cached in st.session_state so feedback reruns
never re-run the expensive pipeline.
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

_PAGE = "_page"   # "welcome" | "form" | "itinerary"


# ── Global CSS ────────────────────────────────────────────────────────────────

_CSS = """
<style>
/* ══════════════════════════════════════════════════════
   BASE — white canvas, sky-blue accents
══════════════════════════════════════════════════════ */
.stApp { background: #FFFFFF; }
.block-container { padding: 2rem 2.5rem 4rem; max-width: 1280px; }

h1 { font-size: 2.2rem !important; font-weight: 800 !important;
     color: #0F172A !important; letter-spacing: -.5px; }
h2 { font-size: 1.35rem !important; font-weight: 700 !important;
     color: #0F172A !important; }
h3 { font-size: 1.05rem !important; font-weight: 600 !important;
     color: #1E293B !important; }
p, li { color: #334155; }
hr  { border-color: #E0F2FE !important; margin: 1.25rem 0 !important; }
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-thumb { background: #BAE6FD; border-radius: 3px; }

/* ══════════════════════════════════════════════════════
   PAGE 2 — FORM TOP-NAV
══════════════════════════════════════════════════════ */
.form-topnav {
    display: flex; align-items: center; gap: .75rem;
    margin-bottom: 1.25rem;
    padding-bottom: .75rem;
    border-bottom: 1px solid #E0F2FE;
}
.form-topnav-title {
    font-weight: 700; font-size: 1.1rem; color: #0F172A;
}

/* ══════════════════════════════════════════════════════
   ONBOARDING — PROGRESS BAR
══════════════════════════════════════════════════════ */
.onb-progress {
    display: flex; align-items: flex-start; justify-content: center;
    gap: 0; padding: 1.25rem 1rem .9rem;
    background: white; border-radius: 16px;
    border: 1px solid #E0F2FE;
    box-shadow: 0 1px 6px rgba(14,165,233,.07);
}
.step-item  { display: flex; flex-direction: column; align-items: center; gap: 6px; }
.step-conn  { width: 56px; height: 2px; background: #BAE6FD;
              margin-top: 17px; flex-shrink: 0; }
.step-dot {
    width: 34px; height: 34px; border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-weight: 700; font-size: 13px;
    border: 2px solid #BAE6FD; background: #F0F9FF; color: #7DD3FC;
}
.step-dot.done   { background: #DCFCE7; border-color: #22C55E; color: #16A34A; }
.step-dot.active {
    background: #0EA5E9; border-color: transparent; color: white;
    box-shadow: 0 3px 12px rgba(14,165,233,.4);
}
.step-lbl        { font-size: .71rem; font-weight: 500; color: #94A3B8; white-space: nowrap; }
.step-lbl-active { color: #0EA5E9 !important; font-weight: 700 !important; }

/* ══════════════════════════════════════════════════════
   ONBOARDING — STEP HEADER
══════════════════════════════════════════════════════ */
.step-hdr { display: flex; align-items: center; gap: 1rem; margin-bottom: 1.25rem; }
.step-hdr-icon {
    font-size: 1.9rem; color: #0EA5E9; line-height: 1;
    background: #E0F2FE; border-radius: 12px;
    width: 48px; height: 48px;
    display: inline-flex; align-items: center; justify-content: center;
    flex-shrink: 0;
}

/* ══════════════════════════════════════════════════════
   ONBOARDING — DESTINATION CARD
══════════════════════════════════════════════════════ */
.dest-card {
    display: flex; align-items: center; gap: 1rem;
    padding: 1rem 1.25rem;
    background: linear-gradient(135deg, #F0F9FF 0%, #E0F2FE 100%);
    border: 2px solid #7DD3FC; border-radius: 14px;
}
.dest-flag  { font-size: 2rem; }
.dest-name  { font-weight: 700; font-size: 1rem; color: #0F172A; }
.dest-tags  { font-size: .8rem; color: #64748B; margin-top: 2px; }
.dest-check {
    margin-left: auto; background: #0EA5E9; color: white;
    width: 24px; height: 24px; border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-size: .75rem; font-weight: 700;
}

/* ══════════════════════════════════════════════════════
   ONBOARDING — SUMMARY CARD (Review step)
══════════════════════════════════════════════════════ */
.sum-card {
    background: #F0F9FF; border: 1px solid #BAE6FD;
    border-radius: 14px; padding: .9rem 1.25rem;
    display: flex; flex-direction: column; gap: .55rem;
}
.sum-row { display: flex; align-items: flex-start; gap: .75rem; }
.sum-key { font-size: .82rem; color: #0284C7; font-weight: 600; min-width: 120px; }
.sum-val { font-size: .88rem; color: #0F172A; font-weight: 500; }

/* ══════════════════════════════════════════════════════
   st.pills
══════════════════════════════════════════════════════ */
div[data-testid="stPills"] { gap: 8px !important; flex-wrap: wrap !important; }
div[data-testid="stPills"] button {
    border-radius: 22px !important; padding: .45rem 1.15rem !important;
    font-size: .88rem !important; font-weight: 600 !important;
    border: 2px solid #BAE6FD !important;
    background: white !important; color: #0284C7 !important;
    transition: all .15s ease !important;
}
div[data-testid="stPills"] button[aria-selected="true"] {
    background: #0EA5E9 !important; border-color: transparent !important;
    color: white !important; box-shadow: 0 3px 10px rgba(14,165,233,.35) !important;
}
div[data-testid="stPills"] button:hover:not([aria-selected="true"]) {
    border-color: #0EA5E9 !important; color: #0284C7 !important;
    background: #F0F9FF !important;
}

/* ══════════════════════════════════════════════════════
   BUTTONS
══════════════════════════════════════════════════════ */
.stButton > button {
    border-radius: 10px; font-weight: 600;
    border: 1.5px solid #BAE6FD; transition: all .15s ease; color: #0284C7;
}
.stButton > button[kind="primary"],
.stButton > button[data-testid="baseButton-primary"] {
    background: #0EA5E9 !important; border: none !important;
    color: white !important; font-size: .95rem !important;
    box-shadow: 0 2px 10px rgba(14,165,233,.28) !important;
}
.stButton > button[kind="primary"]:hover {
    transform: translateY(-1px) !important;
    box-shadow: 0 5px 18px rgba(14,165,233,.42) !important;
    background: #0284C7 !important;
}

/* ══════════════════════════════════════════════════════
   PAGE 3 — ITINERARY HEADER BAR
══════════════════════════════════════════════════════ */
.itin-header {
    display: flex; align-items: center; justify-content: space-between;
    background: linear-gradient(135deg, #F0F9FF, #E0F2FE);
    border: 1px solid #BAE6FD; border-radius: 16px;
    padding: 1rem 1.5rem; margin-bottom: 1rem;
    box-shadow: 0 2px 10px rgba(14,165,233,.1);
}
.itin-header-text { font-size: 1.15rem; font-weight: 700; color: #0F172A; }
.itin-header-text span { color: #0EA5E9; }

/* ══════════════════════════════════════════════════════
   BORDERED CONTAINERS (venue cards)
══════════════════════════════════════════════════════ */
div[data-testid="stVerticalBlockBorderWrapper"] {
    border-radius: 14px !important; border: 1px solid #E0F2FE !important;
    background: white !important;
    box-shadow: 0 1px 4px rgba(14,165,233,.06) !important;
    transition: box-shadow .2s ease; overflow: hidden;
}
div[data-testid="stVerticalBlockBorderWrapper"]:hover {
    box-shadow: 0 4px 16px rgba(14,165,233,.14) !important;
    border-color: #BAE6FD !important;
}

/* ══════════════════════════════════════════════════════
   ITINERARY TABS
══════════════════════════════════════════════════════ */
.stTabs [data-baseweb="tab-list"] {
    gap: 4px; background: #F0F9FF; border-radius: 12px;
    padding: 4px; border: 1px solid #BAE6FD;
    box-shadow: 0 1px 4px rgba(14,165,233,.08); margin-bottom: .5rem;
}
.stTabs [data-baseweb="tab"] {
    border-radius: 8px; padding: 8px 20px;
    font-weight: 600; font-size: .88rem; color: #0284C7;
    border: none !important; background: transparent; transition: all .15s;
}
.stTabs [aria-selected="true"] {
    background: #0EA5E9 !important; color: white !important;
    box-shadow: 0 2px 8px rgba(14,165,233,.3) !important;
}
.stTabs [data-baseweb="tab-panel"] { padding-top: .75rem; }

/* ══════════════════════════════════════════════════════
   VENUE CARDS
══════════════════════════════════════════════════════ */
.feedback-row .stButton > button {
    border-radius: 8px; font-size: .8rem; font-weight: 600;
    border: 1.5px solid #BAE6FD; background: #F0F9FF; color: #0284C7;
}
.feedback-row .stButton > button:hover {
    border-color: #0EA5E9; background: white; color: #0EA5E9;
}
.leg-connector {
    display: flex; align-items: center; gap: 8px;
    margin: 2px 0 2px 4px; color: #7DD3FC; font-size: .8rem;
}

/* ══════════════════════════════════════════════════════
   MISC
══════════════════════════════════════════════════════ */
.stSuccess, .stInfo, .stWarning, .stError { border-radius: 10px !important; }
.stExpander { border-radius: 10px !important; border: 1px solid #E0F2FE !important; }
details[open] > summary { font-weight: 600; }
</style>
"""


def _inject_css() -> None:
    # Bootstrap Icons font — loaded first so <i class="bi ..."> works everywhere
    st.markdown(
        '<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css">',
        unsafe_allow_html=True,
    )
    st.markdown(_CSS, unsafe_allow_html=True)


def _scroll_to_top() -> None:
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


def _go(page: str) -> None:
    """Navigate to a page, scroll to top, and rerun."""
    st.session_state[_PAGE] = page
    st.session_state["_scroll_top"] = True
    st.rerun()


# ── Pages ─────────────────────────────────────────────────────────────────────

def _page_welcome() -> None:
    st.markdown("<div style='height:6rem'></div>", unsafe_allow_html=True)

    _, mid, _ = st.columns([1, 4, 1])
    with mid:
        st.markdown(
            """<div style="text-align:center;margin-bottom:2rem">
                <i class="bi bi-compass"
                   style="font-size:3.2rem;color:#0EA5E9;display:block;margin-bottom:1rem"></i>
                <h1 style="font-size:2.4rem!important;margin-bottom:.6rem">
                    Hi! Ready to explore?
                </h1>
                <p style="color:#64748B;font-size:1.05rem;margin:0">
                    Let's build your perfect day-by-day travel itinerary.
                </p>
            </div>""",
            unsafe_allow_html=True,
        )
        _, btn_col, _ = st.columns([1, 2, 1])
        with btn_col:
            if st.button("Let's go  →", type="primary",
                         use_container_width=True, key="wlc_go"):
                _go("form")


def _page_form() -> None:
    # ── Top nav ────────────────────────────────────────────────────────────────
    if st.button("← Back", key="form_back_btn"):
        _go("welcome")

    st.markdown("<div style='height:.25rem'></div>", unsafe_allow_html=True)

    # ── Centred multi-step form ────────────────────────────────────────────────
    _, form_col, _ = st.columns([1, 6, 1])
    with form_col:
        preferences = render_preference_form()

    # ── On final submit: run pipeline → itinerary page ─────────────────────────
    if preferences is not None:
        clear_itinerary_state()
        _run_pipeline(preferences)
        _go("itinerary")


def _page_itinerary() -> None:
    # Guard: if session state was lost (e.g. hard reload) bounce back to welcome
    state = load_itinerary_state()
    if not state:
        _go("welcome")
        return

    dest = state["preferences"]["destination"]
    days = state["preferences"]["days"]

    # ── Header bar ─────────────────────────────────────────────────────────────
    hdr_left, hdr_right = st.columns([5, 2])
    with hdr_left:
        st.markdown(
            f"""<div class="itin-header">
                <span class="itin-header-text">
                    <i class="bi bi-check-circle-fill" style="color:#22C55E"></i>
                    Your {days}-day itinerary for
                    <span>{dest}</span> is ready!
                </span>
            </div>""",
            unsafe_allow_html=True,
        )
    with hdr_right:
        st.markdown("<div style='height:.35rem'></div>", unsafe_allow_html=True)
        if st.button("← Plan another trip",
                     use_container_width=True, key="plan_again"):
            clear_itinerary_state()
            _go("welcome")

    # ── Itinerary tabs ──────────────────────────────────────────────────────────
    render_itinerary(
        itinerary=state["itinerary"],
        clusters=state["clusters"],
        issues=state["issues"],
        itinerary_id=state["itinerary_id"],
        venue_lookup=state["venue_lookup"],
    )

    with st.expander("🔧 Debug — preferences", expanded=False):
        st.json(state["preferences"])


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

    # Scroll to top on every page transition (set by _go() and swap handler)
    if st.session_state.pop("_scroll_top", False):
        _scroll_to_top()

    page = st.session_state.get(_PAGE, "welcome")
    if page == "welcome":
        _page_welcome()
    elif page == "form":
        _page_form()
    elif page == "itinerary":
        _page_itinerary()
    else:
        _go("welcome")


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
