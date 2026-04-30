# CLAUDE.md

This file provides guidance to Claude Code when working with this project.

## Project Overview

**Name:** AI Personal Travel Itinerary Generator
**Type:** Academic prototype for AI Solution Design and Prototype Evaluation assignment
**Goal:** Generate geographically coherent, preference-matched, day-by-day travel itineraries for a single destination using a hybrid AI pipeline (LLM + embeddings + clustering + rule-based validation).

### Problem Statement

Independent travelers spend 8-15 hours researching multi-day trips across blogs, Reddit, Google Maps, and review sites, and still produce itineraries that are geographically inefficient, miss stated preferences, or include closed/wrong venues. This system reduces that to ~2 minutes of input and produces a feasible, grounded itinerary.

### Scope Boundaries

**In scope:** Single-destination, 2-7 day leisure trips, day-by-day itinerary with venues, timing, and travel logistics.

**Out of scope:** Flight booking, hotel booking, payments, multi-city routing, real-time re-planning during the trip, multi-user collaboration.

### Success Definition

User provides destination + dates + preferences in under 2 minutes and receives an itinerary that is:
- Geographically coherent (intra-day travel time < 20 min average)
- Preference-matched (≥80% precision on top-10 venues)
- Feasible (zero opening-hours violations, zero hallucinated venues)
- Grounded in real, currently-operating venues

---

## Architecture

### 8-Stage AI Pipeline

1. **Input & preference extraction** — Form fields + free-text → LLM with structured output → normalized preference object
2. **Candidate venue retrieval** — Overpass/OSM (primary) or Foursquare (fallback) → 100-200 venues per destination, cached in SQLite
3. **Enrichment & scoring** — Build venue text descriptions from OSM tags → embed with sentence-transformers → cosine similarity ranking against user preferences
4. **Geographic clustering** — k-means on lat/long with k = trip_days → each cluster = one day
5. **Itinerary assembly** — LLM (Groq Llama 3.3 70B) with structured JSON output, one call per day's cluster
6. **Validation layer** — Rule-based checks for hallucinations, opening hours, travel time, rating thresholds
7. **Presentation & feedback** — Streamlit UI with Folium maps, thumbs up/down, "swap this" buttons, all events logged
8. **Feedback loop** — Logged events stored in SQLite for future preference weight tuning and itinerary quality dataset

### Hybrid AI Justification

This is **not** an LLM wrapper. Each technique is chosen for its problem fit:
- **Embeddings** for semantic preference→venue matching (natural language, heterogeneous descriptions)
- **Unsupervised clustering** for day-grouping (geographic constraint is mathematical, not linguistic)
- **Generative AI** for itinerary composition (requires fluent narrative + contextual reasoning)
- **Rule-based validation** as guardrail (hallucinations are unacceptable in travel)

---

## Tech Stack

| Layer | Tool | Notes |
|---|---|---|
| Venue data | Overpass API (OSM) | Free, no key. Fallback: Foursquare free tier |
| Geocoding | Nominatim (OSM) | Free, 1 req/sec rate limit |
| Travel times | OpenRouteService | Free key, 2000 req/day |
| Weather | Open-Meteo | Free, no key needed |
| LLM | Groq API (Llama 3.3 70B) | Generous free tier, fast inference, JSON mode |
| Embeddings | sentence-transformers (`all-MiniLM-L6-v2`) | Local, free, fast |
| Vector ops | FAISS or numpy | In-memory is fine for prototype |
| Clustering | scikit-learn (KMeans, DBSCAN) | Standard |
| Backend | Python 3.10+, FastAPI optional | Streamlit may be enough |
| Frontend | Streamlit + Folium + streamlit-folium | Speed over polish |
| Storage | SQLite | Zero setup |
| PDF export | reportlab or pdfkit | Phase 3 feature |
| Hosting | Streamlit Community Cloud | Free |

**Total cost target: ₹0**

### Required Environment Variables (.env)

```
GROQ_API_KEY=
ORS_API_KEY=
# Optional fallbacks:
FOURSQUARE_API_KEY=
GOOGLE_PLACES_API_KEY=
```

---

## Project Structure

```
travel-agent/
├── CLAUDE.md                  # This file
├── README.md
├── requirements.txt
├── .env                       # Gitignored
├── .env.example
├── data/
│   ├── travel.db              # SQLite
│   └── cache/                 # Cached API responses
├── src/
│   ├── __init__.py
│   ├── config.py              # Env loading, constants
│   ├── db.py                  # SQLite schema + helpers
│   ├── ingestion/
│   │   ├── overpass.py        # OSM venue fetching
│   │   ├── nominatim.py       # Geocoding
│   │   └── enrichment.py      # Build venue text descriptions
│   ├── matching/
│   │   ├── embeddings.py      # sentence-transformers wrapper
│   │   └── scoring.py         # Hard filters + similarity ranking
│   ├── clustering/
│   │   └── geo_clusters.py    # k-means / DBSCAN day grouping
│   ├── generation/
│   │   ├── prompts.py         # All LLM prompt templates
│   │   ├── extractor.py       # Free-text → preference JSON
│   │   └── itinerary.py       # Cluster → day itinerary JSON
│   ├── validation/
│   │   └── checks.py          # Hallucination, hours, travel time
│   ├── routing/
│   │   └── ors.py             # OpenRouteService travel times
│   ├── weather/
│   │   └── open_meteo.py      # Phase 3
│   └── ui/
│       ├── app.py             # Streamlit entrypoint
│       ├── forms.py           # Input components
│       ├── itinerary_view.py  # Day tabs, venue cards
│       └── map_view.py        # Folium map rendering
├── eval/
│   ├── preference_test_set.json
│   ├── itinerary_rubric.md
│   ├── run_eval.py
│   └── results/
├── notebooks/                 # Exploration only, not production
└── tests/
    └── test_*.py
```

---

## Database Schema (SQLite)

```sql
CREATE TABLE venues (
    id INTEGER PRIMARY KEY,
    osm_id TEXT UNIQUE,
    destination TEXT,
    name TEXT NOT NULL,
    lat REAL NOT NULL,
    lon REAL NOT NULL,
    categories TEXT,          -- JSON array
    tags TEXT,                -- JSON, raw OSM tags
    description TEXT,         -- Built for embedding
    rating REAL,
    price_level INTEGER,      -- 1-4
    opening_hours TEXT,       -- OSM format
    embedding BLOB,           -- Cached vector
    fetched_at TIMESTAMP
);

CREATE TABLE itineraries (
    id INTEGER PRIMARY KEY,
    user_id TEXT,             -- Hardcoded or session
    destination TEXT,
    preferences TEXT,         -- JSON
    days INTEGER,
    output TEXT,              -- Full itinerary JSON
    created_at TIMESTAMP
);

CREATE TABLE feedback (
    id INTEGER PRIMARY KEY,
    itinerary_id INTEGER,
    venue_id INTEGER,
    day_number INTEGER,
    action TEXT,              -- 'thumbs_up', 'thumbs_down', 'swap'
    created_at TIMESTAMP,
    FOREIGN KEY (itinerary_id) REFERENCES itineraries(id),
    FOREIGN KEY (venue_id) REFERENCES venues(id)
);

CREATE INDEX idx_venues_destination ON venues(destination);
CREATE INDEX idx_feedback_itinerary ON feedback(itinerary_id);
```

---

## Build Phases

### Phase 0: Setup (Day 1, ~3 hrs)

- [x] Create repo, virtualenv, requirements.txt
- [x] Get Groq API key, ORS API key
- [x] Pick primary destination (default: Goa or Mumbai)
- [x] Initialize SQLite with schema above
- [x] Verify each API responds with a "hello world" script

**Deliverable:** Empty repo with verified API connections.

---

### Phase 1: Minimum Viable Prototype (Days 2-6, ~15-20 hrs)

**Goal:** End-to-end working demo. User input → itinerary on map. Ugly but functional. **This alone is a submittable prototype.**

#### 1.1 Venue ingestion (Day 2)
- Geocode destination via Nominatim
- Query Overpass API for tourism, amenity (restaurants, cafes), leisure, shop POIs in radius
- Parse OSM tags into structured fields
- Cache in SQLite `venues` table — never re-fetch during demo
- Target: 100-200 venues for primary destination

#### 1.2 Preference input (Day 3 AM)
- Streamlit form: destination dropdown (1 city for MVP), days slider (2-7), party size, budget tier, interest checkboxes (food, history, nature, nightlife, shopping, art, beaches), pace (relaxed/moderate/packed)
- Skip free-text input for Phase 1 — added in Phase 2

#### 1.3 Preference matching (Day 3 PM)
- Build venue description string from OSM tags (e.g., "Italian restaurant, mid-range, outdoor seating")
- Embed all venue descriptions once with `all-MiniLM-L6-v2`, cache vectors in `venues.embedding`
- Embed user preferences as a single sentence at query time
- Apply hard filters first (budget, category match), then rank top 30-50 by cosine similarity

#### 1.4 Geographic clustering (Day 4 AM)
- k-means on (lat, lon) of top-scored venues, k = trip_days
- Each cluster = one day's candidate pool
- Sanity check: visualize clusters on map, fall back to DBSCAN if k-means produces overlapping clusters

#### 1.5 LLM itinerary assembly (Day 4 PM)
- One Groq call per day's cluster
- Structured prompt: "Given these venues, create a one-day itinerary with breakfast, morning activity, lunch, afternoon activity, dinner. Output JSON: {schema}"
- Use Groq's JSON mode for clean parsing
- Limit 4-6 venues per day
- Include opening hours in prompt context where available

#### 1.6 Display (Day 5)
- Streamlit page with day tabs
- Per day: Folium map with numbered markers + lines connecting venues + list view (name, suggested time, category, LLM one-liner description)
- This is the **value moment** — should feel magical

#### 1.7 Polish for demo (Day 6)
- Loading spinner during generation
- Error handling for API failures
- Sensible defaults
- "Try sample input" button for smooth demos
- Test with 3-4 preference combinations to verify output varies meaningfully

**Phase 1 done = demo video can be recorded.**

---

### Phase 2: Quality & Rigor (Days 7-10, ~10-12 hrs)

**Goal:** Trustworthy outputs and rigorous evaluation. **This is where data-centric thinking and metrics points are earned.**

#### 2.1 Free-text preference extraction (Day 7 AM)
- Add textarea: "Tell me about your ideal trip"
- LLM extraction with strict JSON schema
- Merge with form fields (form overrides on conflict)
- Provides the LLM-for-extraction story for the report

#### 2.2 Travel time estimation (Day 7 PM)
- OpenRouteService for walking/driving times between consecutive venues per day
- Display times in itinerary view
- Flag days with total transit > 90 min

#### 2.3 Validation layer (Day 8 AM)
Programmatically check each itinerary:
- **Hallucination:** any venue not in candidate set → reject and regenerate
- **Opening hours:** suggested time outside venue hours → flag
- **Travel time overflow:** total transit > threshold → flag
- **Rating threshold:** any venue < 3.5 stars → flag
- Auto-fix by regenerating that day, or display warnings

#### 2.4 Feedback UI (Day 8 PM)
- Thumbs up/down per venue
- "Swap this" button → regenerate single venue from candidate pool
- Log all events to SQLite `feedback` table with full context
- No retraining in prototype — but logging enables concrete feedback loop description in report

#### 2.5 Build evaluation set (Day 9)
**Critical for metrics section:**
- **Preference extraction test set:** 20-30 hand-written free-text inputs with ground-truth preference JSON. Compute field-level accuracy.
- **Itinerary quality rubric:** 10 generated itineraries scored 1-5 on feasibility, preference match, diversity, groundedness. Self-score; if time, get 2-3 friends for inter-rater reliability.
- **Geographic coherence test:** 10 itineraries, compute distribution of average intra-day travel time.

#### 2.6 Small user study (Day 10)
- 5-8 participants (classmates, family, friends who travel)
- Each generates one itinerary for a destination they know
- Collect: 1-5 satisfaction rating, edit rate (% venues they'd swap), "would you actually use this?" yes/no, free-text feedback
- Provides real outcome metrics for the report

---

### Phase 3: Polish & Differentiation (Days 11-13, ~6-8 hrs)

**Goal:** Professional appearance + 1-2 memorable features. **Pick only 1-2, don't try all.**

#### Option A: Weather-aware scheduling
- Open-Meteo forecast for trip dates
- Push outdoor activities to clear days, indoor to rainy days
- Strong differentiator, genuinely free API

#### Option B: Map polish
- Custom Folium icons by category (fork=food, star=attraction, etc.)
- Numbered route lines showing day flow
- Popups with photos from Wikipedia/Wikimedia (free)

#### Option C: Multi-destination support
- Pre-cache 2-3 cities (e.g., Goa, Mumbai, Bangalore)
- Demonstrates generalization without infinite scope
- No need for 50 cities — 3 well-cached tells the story

#### Option D: PDF export
- `reportlab` or `pdfkit` for printable itinerary
- Tangible, demo-friendly, screenshots well in report

#### Option E: Persona presets
- Buttons: "Foodie weekend," "Family with kids," "Solo backpacker," "Honeymoon"
- Pre-fill preferences
- Fast to implement, makes demo flow smoother

---

### Phase 4: Documentation & Submission (Days 14-15, ~8 hrs)

#### 4.1 Pipeline diagram
- Tool: draw.io / Excalidraw / PowerPoint
- Show 8-stage architecture, data sources, feedback loop
- One clean diagram > three messy ones

#### 4.2 Stack diagram/table
- Visual table: layer × tool × one-line justification

#### 4.3 Written report (10-15 pages)
Map sections directly to assignment deliverables:
1. Problem definition and context
2. Data and AI factory design
3. AI techniques and technology stack
4. Prototype description
5. Success metrics
6. Go/no-go evaluation

The phased build provides content for nearly every section directly.

#### 4.4 Demo video (2-3 min)
Script:
- 0:00-0:20 — Problem framing
- 0:20-0:50 — Show input form
- 0:50-1:50 — Generate and walk through itinerary
- 1:50-2:20 — Show map and one feedback action
- 2:20-2:40 — Mention metrics and next steps

Tools: OBS (free) or Zoom recording. Don't over-produce.

#### 4.5 Final pass
- Run prototype 5 times with different inputs
- Fix any breakages
- Pre-cache demo destination so live API calls aren't required during presentation

---

## Metrics & Go/No-Go Criteria

### Model / Pipeline Metrics

| Metric | Target | How measured |
|---|---|---|
| Preference extraction accuracy | ≥90% | Field-level match on 30-input test set |
| Retrieval precision@10 | ≥80% | Manual rating of top-10 venues |
| Geographic coherence | <20 min avg | Avg intra-day travel between consecutive venues |
| Groundedness | 100% | % recommended venues present in candidate set |
| Constraint satisfaction | ≥95% | % itineraries with zero opening-hours violations |
| Latency | <30 sec | End-to-end generation time |

### Outcome Metrics

| Metric | Target | How measured |
|---|---|---|
| Time-to-itinerary | ~2 min vs ~10 hrs manual | Self-reported / observed |
| User satisfaction | ≥4.0 / 5 | Rubric mean across user study |
| Edit rate | ≥70% kept | % venues users don't swap |
| Booking intent | ≥60% yes | "Would you actually use this?" survey |

### Go / No-Go Thresholds

- **Go:** Groundedness 100% AND constraint satisfaction ≥95% AND user rating ≥4.0 AND edit rate ≥70%
- **Conditional Go:** Groundedness 100% but ratings 3.5-4.0 → invest in preference modeling
- **No-Go:** Groundedness <100% OR ratings <3.5 (hallucination is trust-killer in travel)

### Risks Identified

- API cost at scale (mitigated by caching, OSM-first)
- Hallucination of venues or hours (mitigated by validation layer)
- Limited coverage outside major cities (acknowledged scope limit)
- Cold-start without user feedback (designed loop, not yet trained)
- Review-rating bias (popular ≠ good fit; mitigated partly by preference matching)

---

## Coding Conventions

- Python 3.10+, type hints everywhere
- `black` for formatting, `ruff` for linting
- All API calls wrapped with retry + timeout (use `tenacity`)
- All external data cached in SQLite — never hit live APIs during demo
- All LLM prompts in `src/generation/prompts.py` as named constants — never inline strings
- Log to `data/logs/app.log`, not print()
- `.env` for secrets, never commit

## Important Behavioral Rules for Claude Code

- **Always cache before fetching.** Check SQLite first, hit API only on miss.
- **Never invent venue data.** If a field is missing from OSM, mark it as `None`, don't fill it in.
- **Validate LLM JSON outputs.** Always parse with try/except and re-prompt on failure.
- **Don't add features beyond the current phase.** Phase discipline matters — Phase 1 should not contain Phase 3 features.
- **Don't switch LLM providers mid-build.** Stick with Groq throughout unless it fails outright.
- **Don't build auth/login.** Hardcode `user_id = "demo_user"` for the prototype.
- **Don't try to scrape sites without APIs.** If a data source needs scraping, find an API alternative or skip it.
- **Always include opening hours in LLM prompts when available** — the validation layer depends on this.
- **Limit LLM context size.** Pass only the day's cluster venues, not all candidates.

## Demo Day Checklist

- [ ] Primary destination fully cached (no live API calls needed)
- [ ] 3+ preset preference combinations tested and working
- [ ] Sample input button populates form correctly
- [ ] Map renders without errors
- [ ] Validation layer catches at least one issue in a deliberately broken test
- [ ] Feedback buttons log to SQLite
- [ ] Network failure scenario tested (graceful degradation)
- [ ] Demo video uploaded and accessible
- [ ] Report PDF finalized
- [ ] Repo README has setup instructions

---

## Quick Reference: Common Commands

```bash
# Setup
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r requirements.txt

# Initialize DB
python -m src.db init

# Pre-cache a destination
python -m src.ingestion.overpass --destination "Goa, India"

# Run app
streamlit run src/ui/app.py

# Run evaluation
python -m eval.run_eval

# Run tests
pytest tests/
```

---

## Assignment Mapping

| Assignment Deliverable | Built In | Located In |
|---|---|---|
| Problem statement | Phase 0 | Report §1, this file |
| Data design | Phase 1.1, 2.5 | Report §2, `src/ingestion/` |
| AI factory diagram | Phase 4.1 | Report §2 appendix |
| Pipeline explanation | Phase 1-2 | Report §2 |
| Technique justification | All phases | Report §3 |
| Stack diagram | Phase 4.2 | Report §3 appendix |
| Working prototype | Phase 1-3 | `src/` |
| Tech description (1pg) | Phase 4.3 | Report §4 |
| Demo video | Phase 4.4 | Submitted separately |
| Model metrics | Phase 2.5 | Report §5, `eval/results/` |
| Outcome metrics | Phase 2.6 | Report §5 |
| Go/no-go evaluation | Phase 4.3 | Report §6 |
