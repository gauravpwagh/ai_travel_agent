"""All LLM prompt templates as named constants.

Never write prompt strings inline — import from here.
"""

# ── Day itinerary assembly ────────────────────────────────────────────────────

DAY_ITINERARY_SYSTEM = """\
You are an expert travel planner. Your job is to build a realistic, \
enjoyable one-day itinerary from a provided list of real venues.

Rules you must follow:
- Use ONLY venues from the provided list. Do not invent or hallucinate venues.
- Select 4 to 6 venues that make a logical, geographically sensible day.
- Schedule activities in chronological order starting around 08:00.
- Respect opening hours where provided — do not schedule a venue outside its hours.
- Keep total travel time between consecutive venues reasonable (< 30 min each leg).
- Write a vivid but concise description (1-2 sentences) for each slot.
- Output ONLY valid JSON matching the schema exactly. No prose outside the JSON.\
"""

# Placeholders: {day_number}, {destination}, {date_label}, {budget_tier},
# {pace_label}, {interests}, {venue_list}, {schema}
DAY_ITINERARY_USER = """\
Build a one-day itinerary for Day {day_number} in {destination}.

Traveller profile:
- Budget: {budget_tier}
- Pace: {pace_label}
- Interests: {interests}

Available venues (use osm_id exactly as shown):
{venue_list}

Output JSON with this exact schema:
{schema}

Remember: only use venues from the list above. Include the exact osm_id for each slot.\
"""

# Used on the second attempt after a JSON parse failure
DAY_ITINERARY_RETRY = """\
Your previous response could not be parsed as valid JSON. \
Return ONLY the JSON object — no explanation, no markdown fences, no extra text. \
Use this exact schema:
{schema}\
"""

# ── Schema shown to the LLM ───────────────────────────────────────────────────

DAY_ITINERARY_SCHEMA = """\
{
  "day_number": <integer>,
  "theme": "<short evocative title for the day, e.g. 'Beaches and Seafood'>",
  "slots": [
    {
      "time": "<HH:MM 24-hour>",
      "venue_name": "<exact name from the venue list>",
      "osm_id": "<exact osm_id from the venue list>",
      "category": "<category string>",
      "duration_minutes": <integer>,
      "description": "<1-2 sentence narrative>",
      "travel_note": "<optional: how to reach the next stop, or null>"
    }
  ]
}\
"""
