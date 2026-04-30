"""Geographic day-clustering: k-means (primary) with DBSCAN fallback.

Given top-ranked venues from Phase 1.3, groups them into n_days clusters
so that each cluster becomes one day's candidate pool for the LLM.

Coordinates are scaled to approximate km before clustering so Euclidean
distance is meaningful and the overlap threshold makes geographic sense.

Usage:
    from src.clustering.geo_clusters import cluster_venues

    clusters = cluster_venues(ranked_venues, n_days=3)
    # clusters[0] = list of venue dicts for Day 1, etc.
"""
from __future__ import annotations

import numpy as np
from sklearn.cluster import DBSCAN, KMeans

from src.config import MAX_VENUES_PER_DAY, setup_logging

log = setup_logging()

# Two k-means centroids closer than this (km) are considered overlapping
CENTROID_OVERLAP_KM = 1.0

# DBSCAN neighbourhood radius in km — roughly one walkable city district
DBSCAN_EPS_KM = 2.0
DBSCAN_MIN_SAMPLES = 1

# Max venues passed to the LLM per day (keeps prompt size bounded)
MAX_CLUSTER_SIZE = MAX_VENUES_PER_DAY * 3


# ── Public API ────────────────────────────────────────────────────────────────

def cluster_venues(venues: list[dict], n_days: int) -> list[list[dict]]:
    """Partition venues into n_days geographic day-groups.

    Steps:
      1. Scale lat/lon to km.
      2. Run k-means (k = n_days, 15 restarts).
      3. If any centroid pair is < CENTROID_OVERLAP_KM apart, fall back to DBSCAN.
      4. Sort clusters roughly west→east so days have a logical order.
      5. Cap each cluster at MAX_CLUSTER_SIZE, keeping highest similarity_score.

    Returns a list of n_days lists. If fewer venues than n_days, returns as many
    non-empty clusters as possible.
    """
    if not venues:
        return [[] for _ in range(n_days)]

    if n_days == 1:
        return [_top_venues(venues)]

    if len(venues) < n_days:
        log.warning(
            f"Only {len(venues)} venues for {n_days} days — "
            "some days may have very few venues."
        )

    coords = _scale_coords(venues)

    labels = _run_kmeans(coords, n_days)

    if _centroids_overlap(coords, labels, n_days):
        log.warning(
            "K-means centroids overlap — falling back to DBSCAN."
        )
        labels = _run_dbscan_fallback(coords, n_days, labels)

    clusters = _assign_to_clusters(venues, labels, n_days)
    clusters = _sort_clusters_west_to_east(clusters)
    clusters = [_top_venues(c) for c in clusters]

    _log_cluster_summary(clusters)
    return clusters


# ── Coordinate scaling ────────────────────────────────────────────────────────

def _scale_coords(venues: list[dict]) -> np.ndarray:
    """Convert (lat, lon) to approximate (y_km, x_km).

    At city scale the flat-earth approximation is accurate to < 0.1%.
    """
    lats = np.array([v["lat"] for v in venues], dtype=float)
    lons = np.array([v["lon"] for v in venues], dtype=float)
    mean_lat = float(np.mean(lats))

    y_km = lats * 111.0
    x_km = lons * 111.0 * np.cos(np.radians(mean_lat))
    return np.column_stack([y_km, x_km])


# ── K-means ───────────────────────────────────────────────────────────────────

def _run_kmeans(coords: np.ndarray, k: int) -> np.ndarray:
    k = min(k, len(coords))
    km = KMeans(n_clusters=k, n_init=15, random_state=42)
    labels = km.fit_predict(coords)
    log.info(f"K-means fitted with k={k}, inertia={km.inertia_:.1f}")
    return labels


def _centroids_overlap(
    coords: np.ndarray, labels: np.ndarray, k: int
) -> bool:
    """Return True if any two cluster centroids are closer than CENTROID_OVERLAP_KM."""
    centroids = np.array(
        [coords[labels == i].mean(axis=0) for i in range(k) if np.any(labels == i)]
    )
    if len(centroids) < 2:
        return False
    for i in range(len(centroids)):
        for j in range(i + 1, len(centroids)):
            dist = float(np.linalg.norm(centroids[i] - centroids[j]))
            if dist < CENTROID_OVERLAP_KM:
                log.debug(
                    f"Centroid overlap: cluster {i} and {j} are {dist:.2f} km apart"
                )
                return True
    return False


# ── DBSCAN fallback ───────────────────────────────────────────────────────────

def _run_dbscan_fallback(
    coords: np.ndarray, n_days: int, kmeans_labels: np.ndarray
) -> np.ndarray:
    """Run DBSCAN and coerce the result to exactly n_days labels.

    Strategy:
    - Run DBSCAN with DBSCAN_EPS_KM.
    - Assign noise points (label -1) to nearest non-noise cluster centroid.
    - If too many clusters: merge smallest into nearest until n_days remain.
    - If too few clusters: subdivide the largest via k-means until n_days reached.
    - Fall back to original k-means labels if DBSCAN produces only 1 cluster.
    """
    db = DBSCAN(eps=DBSCAN_EPS_KM, min_samples=DBSCAN_MIN_SAMPLES)
    raw_labels = db.fit_predict(coords)

    unique = set(raw_labels) - {-1}
    log.info(f"DBSCAN produced {len(unique)} clusters (+noise={np.sum(raw_labels == -1)})")

    if len(unique) == 0:
        log.warning("DBSCAN found no clusters — keeping k-means labels.")
        return kmeans_labels

    # Assign noise to nearest cluster centroid
    labels = raw_labels.copy()
    if -1 in labels:
        centroids = {
            lbl: coords[labels == lbl].mean(axis=0) for lbl in unique
        }
        for idx in np.where(labels == -1)[0]:
            nearest = min(unique, key=lambda l: np.linalg.norm(coords[idx] - centroids[l]))
            labels[idx] = nearest

    # Re-label to 0-based consecutive integers
    label_map = {old: new for new, old in enumerate(sorted(set(labels)))}
    labels = np.array([label_map[l] for l in labels])
    n_clusters = len(set(labels))

    # Merge down if too many
    while n_clusters > n_days:
        labels = _merge_closest_clusters(coords, labels)
        n_clusters = len(set(labels))

    # Subdivide up if too few
    while n_clusters < n_days and n_clusters < len(coords):
        labels = _split_largest_cluster(coords, labels)
        n_clusters = len(set(labels))

    return labels


def _merge_closest_clusters(coords: np.ndarray, labels: np.ndarray) -> np.ndarray:
    """Merge the two clusters whose centroids are closest."""
    unique = sorted(set(labels))
    centroids = {l: coords[labels == l].mean(axis=0) for l in unique}
    best_dist, best_pair = float("inf"), (unique[0], unique[1])
    for i in range(len(unique)):
        for j in range(i + 1, len(unique)):
            d = float(np.linalg.norm(centroids[unique[i]] - centroids[unique[j]]))
            if d < best_dist:
                best_dist, best_pair = d, (unique[i], unique[j])
    a, b = best_pair
    new_labels = labels.copy()
    new_labels[labels == b] = a
    # Re-label to consecutive
    label_map = {old: new for new, old in enumerate(sorted(set(new_labels)))}
    return np.array([label_map[l] for l in new_labels])


def _split_largest_cluster(coords: np.ndarray, labels: np.ndarray) -> np.ndarray:
    """Split the largest cluster into two using k-means(k=2)."""
    unique = sorted(set(labels))
    largest = max(unique, key=lambda l: np.sum(labels == l))
    mask = labels == largest
    sub_coords = coords[mask]
    if len(sub_coords) < 2:
        return labels
    sub_labels = KMeans(n_clusters=2, n_init=10, random_state=42).fit_predict(sub_coords)
    new_label = max(unique) + 1
    new_labels = labels.copy()
    idxs = np.where(mask)[0]
    for i, idx in enumerate(idxs):
        if sub_labels[i] == 1:
            new_labels[idx] = new_label
    return new_labels


# ── Cluster assembly ──────────────────────────────────────────────────────────

def _assign_to_clusters(
    venues: list[dict], labels: np.ndarray, n_days: int
) -> list[list[dict]]:
    """Group venues by label into a list of lists."""
    unique = sorted(set(labels))
    clusters: list[list[dict]] = []
    for lbl in unique:
        idxs = [i for i, l in enumerate(labels) if l == lbl]
        clusters.append([venues[i] for i in idxs])
    # Pad with empty lists if we ended up with fewer clusters than n_days
    while len(clusters) < n_days:
        clusters.append([])
    return clusters[:n_days]


def _sort_clusters_west_to_east(clusters: list[list[dict]]) -> list[list[dict]]:
    """Sort clusters by centroid longitude (west first) for geographic day ordering."""
    def centroid_lon(cluster: list[dict]) -> float:
        if not cluster:
            return float("inf")
        return float(np.mean([v["lon"] for v in cluster]))

    return sorted(clusters, key=centroid_lon)


def _top_venues(cluster: list[dict]) -> list[dict]:
    """Keep the highest-scoring venues up to MAX_CLUSTER_SIZE."""
    scored = sorted(
        cluster,
        key=lambda v: v.get("similarity_score", 0.0),
        reverse=True,
    )
    return scored[:MAX_CLUSTER_SIZE]


# ── Logging ───────────────────────────────────────────────────────────────────

def _log_cluster_summary(clusters: list[list[dict]]) -> None:
    for i, cluster in enumerate(clusters):
        if not cluster:
            log.info(f"  Day {i + 1}: 0 venues")
            continue
        lats = [v["lat"] for v in cluster]
        lons = [v["lon"] for v in cluster]
        log.info(
            f"  Day {i + 1}: {len(cluster)} venues, "
            f"centroid ({np.mean(lats):.4f}, {np.mean(lons):.4f})"
        )
