# AI Personal Travel Itinerary Generator

Hybrid AI pipeline (LLM + embeddings + clustering + rule-based validation) that turns user preferences into a feasible, geographically coherent, multi-day travel itinerary for a single destination.

Academic prototype. See [CLAUDE.md](./CLAUDE.md) for full architecture, build phases, and metrics framework.

## Quickstart

```bash
# 1. Clone and enter
cd travel-agent

# 2. Virtualenv + deps
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 3. Configure
cp .env.example .env
# Edit .env and paste your GROQ_API_KEY (free at console.groq.com)
# ORS_API_KEY is optional for Phase 1

# 4. Initialize the database
python -m src.db init

# 5. Verify all APIs respond (Phase 0 deliverable)
python scripts/check_apis.py

# 6. Pre-cache venues for your demo destination (Phase 1.1)
python -m src.ingestion.overpass --destination "Goa, India"

# 7. (Once Phase 1 UI is built)
streamlit run src/ui/app.py
```

## What's built so far

- [x] Phase 0: project scaffold, config, DB schema, API connectivity check
- [x] Phase 1.1: Overpass venue ingestion with OSM tag → category mapping
- [x] Phase 1.2: Streamlit preference form
- [x] Phase 1.3: Embedding-based preference matching
- [x] Phase 1.4: Geographic clustering (k-means)
- [x] Phase 1.5: LLM itinerary assembly (Groq)
- [x] Phase 1.6: Map + day-tab display
- [ ] Phase 2: validation, free-text input, evaluation set, user study
- [ ] Phase 3: 1-2 differentiation features (weather, PDF, multi-city)
- [ ] Phase 4: report, diagrams, demo video

## Project structure

See `CLAUDE.md` § Project Structure.

## Free APIs used

- **Overpass / Nominatim** (OSM) — venues, geocoding. No key.
- **Open-Meteo** — weather. No key.
- **OpenRouteService** — travel times. Free key, 2k req/day.
- **Groq** — LLM (Llama 3.3 70B). Free tier.
- **sentence-transformers** — embeddings. Local, free.

Total cost target: ₹0.
