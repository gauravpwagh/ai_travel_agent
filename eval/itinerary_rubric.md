# Itinerary Quality Rubric — Phase 2.6

Each generated itinerary is scored 1–5 on four dimensions.
Scores are integers. Use half-points (3.5) only when genuinely split.

---

## Dimension 1 — Feasibility

> Does the day plan work in practice? Could a real traveller follow it?

| Score | Criteria |
|-------|----------|
| **5** | All venues are open during their scheduled time slot. Total intra-day transit ≤ 60 min. No venue appears twice. Meal timings are realistic (breakfast 07–10, lunch 12–14, dinner 18–22). |
| **4** | At most one minor timing issue (e.g. a venue opens at 09:00 but is scheduled at 08:30). Transit ≤ 75 min total. |
| **3** | One clear conflict (venue closed at scheduled time) OR transit 75–90 min total. Still mostly followable. |
| **2** | Two conflicts OR transit > 90 min. Day would require significant replanning. |
| **1** | Multiple closed venues, impossible schedule, or transit > 2 hrs. Plan is unusable as-is. |

**Checklist:**
- [ ] Every venue's scheduled time falls within its OSM `opening_hours`
- [ ] Total estimated transit time (ORS or haversine) ≤ 90 min
- [ ] No venue repeated across slots
- [ ] Breakfast/lunch/dinner slots occur at realistic times

---

## Dimension 2 — Preference Match

> Does the itinerary reflect what the traveller asked for?

| Score | Criteria |
|-------|----------|
| **5** | ≥ 90% of venues match at least one stated interest. Budget tier is consistent across all food/shopping picks. Pace (number of venues) matches stated preference. |
| **4** | 75–90% of venues match interests. One budget mismatch or one extra venue beyond pace limit. |
| **3** | 60–75% match. Noticeable budget drift or two extra/missing venues vs pace. |
| **2** | < 60% match. Several venues feel irrelevant to stated interests. |
| **1** | Itinerary appears to ignore stated preferences entirely. |

**Checklist:**
- [ ] Dominant category of each day aligns with user's top interests
- [ ] Restaurants / shops are consistent with stated budget tier
- [ ] Number of daily slots matches pace (relaxed: 4-5, moderate: 5-6, packed: 6+)

---

## Dimension 3 — Diversity

> Does the day offer a varied, interesting mix of experiences?

| Score | Criteria |
|-------|----------|
| **5** | ≥ 3 different category types per day. No consecutive same-category slots (e.g. two restaurants back-to-back). Smooth narrative arc (morning activity → lunch → afternoon activity → dinner). |
| **4** | 2-3 category types per day. One same-category pair but overall flow is good. |
| **3** | Only 2 category types OR two same-category pairs. Day feels slightly monotonous. |
| **2** | Heavily skewed to one category (e.g. 5 restaurants in a day). |
| **1** | No category variety — all slots are the same type. |

**Checklist:**
- [ ] At least 2 distinct category types per day
- [ ] At least one food/cafe slot and at least one non-food slot per day
- [ ] No identical venue names across the multi-day itinerary

---

## Dimension 4 — Groundedness

> Are all recommended venues verifiably real, from the candidate set?

| Score | Criteria |
|-------|----------|
| **5** | Every slot's `osm_id` is present in the candidate venue set. 100% grounded. |
| **4** | One slot has a missing or unresolvable `osm_id` but venue name exists in OSM data. |
| **3** | One hallucinated venue (name not found anywhere in candidate set or OSM). |
| **2** | Two hallucinated venues. |
| **1** | Three or more hallucinated venues, or the itinerary contains entirely invented places. |

**Checklist:**
- [ ] All `osm_id` values resolve to rows in the `venues` SQLite table
- [ ] Venue names match the `name` field in the database (case-insensitive)
- [ ] No venues that don't exist in the Goa OSM dataset

---

## Overall Score

`overall = mean(feasibility, preference_match, diversity, groundedness)`

### Go / No-Go thresholds (from CLAUDE.md)

| Metric | Target | Status |
|--------|--------|--------|
| Groundedness score mean | ≥ 4.5 (≈ 100% venues real) | — |
| Feasibility score mean | ≥ 4.0 | — |
| Preference match mean | ≥ 4.0 (≈ 80% precision) | — |
| Diversity mean | ≥ 3.5 | — |
| **Overall mean** | **≥ 4.0** | — |

---

## How to score an itinerary

1. Open the generated itinerary JSON (from `itineraries` SQLite table or `eval/itinerary_scores.json`).
2. Cross-check each slot's `osm_id` against the `venues` table.
3. Check scheduled time against `opening_hours` in the venue row.
4. Sum travel times from `travel_to_next` fields or re-compute with haversine.
5. Count category types per day.
6. Compare venue categories against stated `preferences.interests`.
7. Assign scores using the tables above. Add brief notes.

---

## Inter-rater reliability

When 2+ evaluators score the same itinerary, compute **Krippendorff's α** across all four dimensions.
Target: α ≥ 0.7 (substantial agreement). Values below 0.5 indicate rubric ambiguity; refine criteria.
