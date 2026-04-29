"""Hard filtering + embedding-based venue ranking against user preferences.

Pipeline:
  1. hard_filter()  — drop venues that can't satisfy budget or interest constraints
  2. rank_venues()  — cosine similarity between preference query and venue vectors

Usage:
    from src.matching.scoring import rank_venues, hard_filter

    filtered = hard_filter(venues, preferences)
    ranked   = rank_venues(filtered, preferences, top_n=50)
"""
from __future__ import annotations

import numpy as np

from src.config import TOP_N_AFTER_RANKING, setup_logging
from src.matching.embeddings import embed_texts, load_embedding

log = setup_logging()

# Maps UI interest labels → OSM-derived category strings (from overpass.py)
INTEREST_TO_CATEGORIES: dict[str, set[str]] = {
    "food": {"food", "cafe"},
    "history": {"history"},
    "nature": {"nature"},
    "nightlife": {"nightlife"},
    "shopping": {"shopping"},
    "art": {"art"},
    "beaches": {"beach"},
}

# price_level values that are excluded per budget tier
# OSM price_level is sparse (mostly None), so only hard-block clear mismatches
BUDGET_EXCLUSIONS: dict[str, set[int]] = {
    "budget": {4},
    "mid-range": set(),
    "luxury": set(),
}


# ── Preference → query string ─────────────────────────────────────────────────

def preference_to_query(preferences: dict) -> str:
    """Convert a preference dict to a natural-language sentence for embedding."""
    interests = preferences.get("interests", [])
    budget = preferences.get("budget_tier", "mid-range")
    pace = preferences.get("pace", "moderate")

    interest_str = " and ".join(interests) if interests else "general sightseeing"
    return (
        f"I enjoy {interest_str}. "
        f"I prefer {budget} options. "
        f"I like a {pace} pace."
    )


# ── Hard filter ───────────────────────────────────────────────────────────────

def hard_filter(venues: list[dict], preferences: dict) -> list[dict]:
    """Drop venues that violate budget or interest constraints.

    A venue passes if:
    - At least one of its categories overlaps with the user's interests, AND
    - Its price_level is not explicitly blocked by the budget tier.

    price_level=None (unknown) is always accepted — OSM data is sparse.
    """
    interests: set[str] = set(preferences.get("interests", []))
    budget: str = preferences.get("budget_tier", "mid-range")

    accepted_cats: set[str] = set()
    for interest in interests:
        accepted_cats |= INTEREST_TO_CATEGORIES.get(interest, set())

    blocked_prices: set[int] = BUDGET_EXCLUSIONS.get(budget, set())

    passed: list[dict] = []
    for venue in venues:
        cats: set[str] = set(venue.get("categories") or [])

        if accepted_cats and not cats & accepted_cats:
            continue  # no category overlap

        price = venue.get("price_level")
        if price is not None and price in blocked_prices:
            continue  # too expensive for budget tier

        passed.append(venue)

    log.info(f"Hard filter: {len(venues)} → {len(passed)} venues")
    return passed


# ── Embedding-based ranking ───────────────────────────────────────────────────

def rank_venues(
    venues: list[dict],
    preferences: dict,
    top_n: int = TOP_N_AFTER_RANKING,
) -> list[dict]:
    """Rank venues by cosine similarity to the preference query.

    Venues without a cached embedding are placed at the end, unranked.
    Adds a 'similarity_score' float key to each returned venue dict.
    """
    with_emb = [v for v in venues if v.get("embedding")]
    without_emb = [v for v in venues if not v.get("embedding")]

    if not with_emb:
        log.warning("No cached embeddings found — returning unranked venues.")
        for v in without_emb:
            v["similarity_score"] = 0.0
        return without_emb[:top_n]

    query = preference_to_query(preferences)
    log.info(f"Ranking {len(with_emb)} venues against query: '{query}'")

    query_vec: np.ndarray = embed_texts([query])[0]  # shape (dim,)

    # Stack all venue vectors into a matrix for a single matmul
    matrix = np.stack([load_embedding(v["embedding"]) for v in with_emb])
    scores: np.ndarray = matrix @ query_vec  # cosine similarities, shape (N,)

    ranked_indices = np.argsort(scores)[::-1]
    ranked = [with_emb[i] for i in ranked_indices]

    for venue, idx in zip(ranked, ranked_indices):
        venue["similarity_score"] = float(scores[idx])

    # Unranked venues get score 0 and are appended after ranked ones
    for v in without_emb:
        v["similarity_score"] = 0.0

    combined = (ranked + without_emb)[:top_n]
    log.info(f"Returning top {len(combined)} ranked venues")
    return combined


# ── Combined entry point ──────────────────────────────────────────────────────

def match_venues(venues: list[dict], preferences: dict) -> list[dict]:
    """Convenience: hard_filter then rank_venues in one call."""
    filtered = hard_filter(venues, preferences)
    return rank_venues(filtered, preferences)
