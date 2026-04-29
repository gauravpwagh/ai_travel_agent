"""sentence-transformers wrapper for venue and preference embedding.

Embeddings are L2-normalised float32 vectors so cosine similarity == dot product.
Vectors are cached in venues.embedding (BLOB) so the model runs once per venue.

Usage:
    from src.matching.embeddings import embed_and_cache, embed_texts, load_embedding
"""
from __future__ import annotations

import numpy as np
from sentence_transformers import SentenceTransformer

from src.config import EMBEDDING_MODEL, setup_logging
from src.db import get_venues_by_destination, update_venue_embedding

log = setup_logging()

_model: SentenceTransformer | None = None


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        log.info(f"Loading embedding model '{EMBEDDING_MODEL}' …")
        _model = SentenceTransformer(EMBEDDING_MODEL)
        log.info("Embedding model ready.")
    return _model


def embed_texts(texts: list[str]) -> np.ndarray:
    """Embed a list of strings. Returns float32 array of shape (N, dim)."""
    model = _get_model()
    return model.encode(
        texts,
        normalize_embeddings=True,  # L2-norm → cosine sim == dot product
        show_progress_bar=False,
        batch_size=64,
    ).astype(np.float32)


def load_embedding(blob: bytes) -> np.ndarray:
    """Deserialise a stored BLOB back to a float32 vector."""
    return np.frombuffer(blob, dtype=np.float32)


def embed_and_cache(destination: str) -> int:
    """Embed descriptions for all venues that lack a cached vector.

    Writes vectors back to venues.embedding. Returns the count embedded.
    """
    venues = get_venues_by_destination(destination)
    to_embed = [v for v in venues if not v.get("embedding")]
    if not to_embed:
        log.info(f"All {len(venues)} venues for '{destination}' already embedded.")
        return 0

    log.info(f"Embedding {len(to_embed)} venues for '{destination}' …")
    texts = [v["description"] or v["name"] for v in to_embed]
    vectors = embed_texts(texts)

    for venue, vec in zip(to_embed, vectors):
        update_venue_embedding(venue["id"], vec.tobytes())

    log.info(f"Embedded and cached {len(to_embed)} venue vectors.")
    return len(to_embed)
