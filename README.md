# AI Personal Travel Itinerary Generator

Hybrid AI pipeline (LLM + embeddings + clustering + rule-based validation) that turns user preferences into a feasible, geographically coherent, multi-day travel itinerary for a single destination.

Academic prototype. See [CLAUDE.md](./CLAUDE.md) for full architecture, build phases, and metrics framework.

## Quickstart

```bash
# 1. Clone and enter
cd travel-agent

# 2. Virtualenv + deps
python -m venv venv
source venv/bin/activate          # Windows: .\venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 3. Configure
cp .env.example .env              # Windows: Copy-Item .env.example .env
# Edit .env and paste your GROQ_API_KEY (free at console.groq.com)
# ORS_API_KEY is required for Phase 2 (free at openrouteservice.org)

# 4. Initialize the database
python -m src.db init

# 5. Verify all APIs respond
python scripts/check_apis.py

# 6. Pre-cache venues for your demo destination
python -m src.ingestion.overpass --destination "Manhattan, New York"

# 7. Run the app
streamlit run src/ui/app.py
```

## Build progress

### Phase 0 — Setup
- [x] Project scaffold, virtualenv, requirements
- [x] DB schema initialized
- [x] API connectivity verified (`scripts/check_apis.py`)
- [x] Primary destination chosen (Manhattan, New York. Goa cached from Phase 1, retained for sparse-data contrast)

### Phase 1 — MVP (complete, demo-able)
- [x] 1.1 Overpass venue ingestion with OSM tag → category mapping
- [x] 1.2 Streamlit preference form (destination, days, party, budget, interests, pace)
- [x] 1.3 Embedding-based preference matching (`all-MiniLM-L6-v2`)
- [x] 1.4 Geographic clustering (k-means, k = trip_days)
- [x] 1.5 LLM itinerary assembly (Groq Llama 3.3 70B, JSON mode)
- [x] 1.6 Map + day-tab display (Folium + Streamlit)
- [x] 1.7 Demo polish (loading state, error handling, sample input button)

### Phase 2 — Quality & rigor (in progress)
- [x] 2.1 Travel-time module (`src/routing/ors.py`) — OpenRouteService wrapper, cached
- [x] 2.2 Validation layer (`src/validation/checks.py`) — hallucination, hours, transit, rating; auto-fix loop
- [x] 2.3 Free-text preference extraction (`src/generation/extractor.py`) — LLM → JSON, merged with form
- [x] 2.4 Feedback UI — thumbs up/down + swap, logs to SQLite *(optional)*
- [x] 2.5 Eval: preference extraction test set (25-30 hand-labeled inputs)
- [x] 2.6 Eval: itinerary quality rubric (10 itineraries × 4 dimensions)
- [x] 2.7 Eval: geographic coherence on Manhattan (10 varied itineraries, median intra-day transit)
- [x] 2.8 Lock metrics in `eval/results/SUMMARY.md`

### Phase 3 — Polish (one feature, picked late)
- [ ] Pick one: weather-aware scheduling, multi-destination support (Mumbai/Bangalore + dropdown), PDF export, persona presets, or map polish

### Phase 4 — Submission
- [ ] Pipeline diagram + stack diagram
- [ ] Written report (10-15 pages)
- [ ] Demo video (2-3 min)
- [ ] Final dry-runs

## Phase 2 quick commands

```bash
# Warm the travel-time cache (after 2.1 lands)
python -m src.routing.ors --warm "Manhattan, New York"

# Run individual eval scripts (after 2.5-2.7 land)
python -m eval.run_extraction_eval     # preference extraction accuracy
python -m eval.run_quality_eval        # itinerary rubric scores
python -m eval.run_coherence_eval      # geographic coherence + groundedness

# Run all evals + write summary
python -m eval.run_eval

# Run validation tests (broken-itinerary smoke test)
pytest tests/test_validation.py -v
```

## Project structure

See `CLAUDE.md` § Project Structure.

## Free APIs used

- **Overpass / Nominatim** (OSM) — venues, geocoding. No key.
- **OpenRouteService** — travel times. Free key, 2k req/day.
- **Open-Meteo** — weather. No key. *(Phase 3 if chosen)*
- **Groq** — LLM (Llama 3.3 70B). Free tier.
- **sentence-transformers** — embeddings. Local, free.

Total cost target: ₹0.

## Phase 2 dependency order (don't reorder)

```
2.1 ORS travel time ─────┐
                         ├─→ 2.2 Validation layer ──┐
                         │                          │
2.3 Free-text extraction ┘                          ├─→ 2.5 Extraction eval
                                                    ├─→ 2.6 Quality rubric eval
                                                    └─→ 2.7 Coherence eval ──→ 2.8 Lock metrics

2.4 Feedback UI is independent — slot in anywhere or skip
```
