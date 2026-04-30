"""Unified evaluation runner — Phases 2.5, 2.6, 2.7.

Tasks
-----
extraction   Phase 2.5 — run extractor against preference_test_set.json,
             compute field-level accuracy and interests F1.
rubric       Phase 2.6 — load itinerary_scores.json, print dimension means
             and go/no-go verdict.
coherence    Phase 2.7 — run the full pipeline on geo_coherence_configs.json,
             compute per-day and median intra-day travel time.
all          Run all three tasks in sequence (default).

Usage
-----
    python -m eval.run_eval                                     # all tasks
    python -m eval.run_eval --task extraction
    python -m eval.run_eval --task rubric
    python -m eval.run_eval --task coherence --destination "Manhattan, New York"
    python -m eval.run_eval --task coherence --destination "Goa, India"
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

# Project root on sys.path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

EVAL_DIR     = Path(__file__).resolve().parent
RESULTS_DIR  = EVAL_DIR / "results"
RESULTS_DIR.mkdir(exist_ok=True)

# ── Helpers ───────────────────────────────────────────────────────────────────

def _load(filename: str) -> dict | list:
    path = EVAL_DIR / filename
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _save(filename: str, data) -> None:
    path = RESULTS_DIR / filename
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"  → saved {path.relative_to(ROOT)}")


def _pct(n: int, d: int) -> str:
    return f"{n}/{d} ({100*n//d}%)" if d else "0/0"


# ── Phase 2.5 — Extraction accuracy ──────────────────────────────────────────

def run_extraction_eval() -> dict:
    from src.generation.extractor import extract_preferences

    dataset = _load("preference_test_set.json")
    cases   = dataset["cases"]
    print(f"\n{'='*60}")
    print(f"PHASE 2.5  Preference Extraction — {len(cases)} cases")
    print(f"{'='*60}")

    scalar_fields = ["days", "party_size", "budget_tier", "pace"]
    # per-field counters: (correct_when_gt_known, total_with_gt, null_predicted_when_gt_known)
    field_stats: dict[str, dict] = {
        f: {"correct": 0, "total": 0, "null_pred": 0} for f in scalar_fields
    }
    interest_f1s: list[float] = []
    case_results: list[dict]  = []

    for i, case in enumerate(cases, 1):
        text     = case["text"]
        expected = case["expected"]
        print(f"\n[{i:02d}/{len(cases)}] {case['id']} ({case['group']})")
        print(f"  Text: {text[:90]}{'…' if len(text)>90 else ''}")

        try:
            extracted = extract_preferences(text)
        except Exception as exc:
            print(f"  ERROR: {exc}")
            extracted = {}

        # Scalar field comparison
        for field in scalar_fields:
            gt  = expected.get(field)
            pred = extracted.get(field)
            if gt is None:
                continue   # ground truth absent — skip (not penalised)
            field_stats[field]["total"] += 1
            if pred is None:
                field_stats[field]["null_pred"] += 1
                print(f"  {field}: GT={gt!r}  PRED=null  ✗ (null)")
            elif pred == gt:
                field_stats[field]["correct"] += 1
                print(f"  {field}: GT={gt!r}  PRED={pred!r}  ✓")
            else:
                print(f"  {field}: GT={gt!r}  PRED={pred!r}  ✗")

        # Interests — precision / recall / F1
        gt_set   = set(expected.get("interests") or [])
        pred_set = set(extracted.get("interests") or [])
        prec = len(gt_set & pred_set) / len(pred_set) if pred_set else (1.0 if not gt_set else 0.0)
        rec  = len(gt_set & pred_set) / len(gt_set)   if gt_set   else (1.0 if not pred_set else 0.0)
        f1   = 2*prec*rec / (prec+rec) if (prec+rec) else 1.0
        interest_f1s.append(f1)
        print(f"  interests: GT={sorted(gt_set)}  PRED={sorted(pred_set)}"
              f"  P={prec:.2f} R={rec:.2f} F1={f1:.2f}")

        case_results.append({
            "id": case["id"], "group": case["group"],
            "extracted": extracted, "expected": expected,
            "interest_f1": round(f1, 3),
        })

        # Polite delay between Groq calls
        if i < len(cases):
            time.sleep(0.5)

    # Summary
    print(f"\n{'─'*60}")
    print("EXTRACTION ACCURACY SUMMARY")
    print(f"{'─'*60}")
    for field, s in field_stats.items():
        tot = s["total"]
        if tot == 0:
            continue
        acc = s["correct"] / tot
        print(f"  {field:<15} acc={acc:.0%}  null_rate={s['null_pred']/tot:.0%}"
              f"  ({_pct(s['correct'], tot)})")

    mean_f1 = sum(interest_f1s) / len(interest_f1s) if interest_f1s else 0
    print(f"  {'interests':<15} mean F1={mean_f1:.3f}")

    overall_correct = sum(s["correct"] for s in field_stats.values())
    overall_total   = sum(s["total"]   for s in field_stats.values())
    print(f"\n  Overall scalar accuracy: {_pct(overall_correct, overall_total)}")
    print(f"  Target: ≥ 90%  →  {'✓ PASS' if overall_total and overall_correct/overall_total >= 0.9 else '✗ FAIL'}")

    result = {
        "task": "extraction",
        "n_cases": len(cases),
        "field_accuracy": {
            f: round(s["correct"]/s["total"], 3) if s["total"] else None
            for f, s in field_stats.items()
        },
        "interests_mean_f1": round(mean_f1, 3),
        "overall_scalar_accuracy": round(overall_correct/overall_total, 3) if overall_total else None,
        "cases": case_results,
    }
    _save("extraction_results.json", result)
    return result


# ── Phase 2.6 — Rubric stats ──────────────────────────────────────────────────

def run_rubric_eval() -> dict:
    data   = _load("itinerary_scores.json")
    items  = data["itineraries"]
    dims   = ["feasibility", "preference_match", "diversity", "groundedness"]

    print(f"\n{'='*60}")
    print(f"PHASE 2.6  Itinerary Quality Rubric — {len(items)} itineraries")
    print(f"{'='*60}")

    dim_scores: dict[str, list[float]] = {d: [] for d in dims}
    rows: list[dict] = []

    for item in items:
        s = item["scores"]
        overall = sum(s[d] for d in dims) / len(dims)
        print(f"  {item['id']}  {item['label'][:40]:<40}"
              f"  F={s['feasibility']}  P={s['preference_match']}"
              f"  D={s['diversity']}  G={s['groundedness']}"
              f"  overall={overall:.2f}")
        for d in dims:
            dim_scores[d].append(s[d])
        rows.append({**item, "computed_overall": round(overall, 2)})

    print(f"\n{'─'*60}")
    print("DIMENSION MEANS")
    print(f"{'─'*60}")
    means: dict[str, float] = {}
    thresholds = {
        "feasibility": 4.0, "preference_match": 4.0,
        "diversity": 3.5,   "groundedness": 4.5,
    }
    for d in dims:
        m    = sum(dim_scores[d]) / len(dim_scores[d])
        tgt  = thresholds[d]
        flag = "✓" if m >= tgt else "✗"
        print(f"  {d:<20} mean={m:.2f}  target≥{tgt}  {flag}")
        means[d] = round(m, 2)

    grand_mean = sum(means.values()) / len(means)
    verdict    = "GO" if all(means[d] >= thresholds[d] for d in dims) else "CONDITIONAL GO / NO-GO"
    print(f"\n  Grand mean:  {grand_mean:.2f}  →  {verdict}")

    result = {
        "task": "rubric", "n_itineraries": len(items),
        "dimension_means": means, "grand_mean": round(grand_mean, 2),
        "verdict": verdict, "itineraries": rows,
    }
    _save("rubric_results.json", result)
    return result


# ── Phase 2.7 — Geographic coherence ─────────────────────────────────────────

def run_coherence_eval(destination: str) -> dict:
    from src.clustering.geo_clusters import cluster_venues
    from src.db import get_venues_by_destination, init_db
    from src.generation.itinerary import build_itinerary
    from src.matching.embeddings import embed_and_cache
    from src.matching.scoring import match_venues
    from src.routing.ors import annotate_itinerary_travel_times

    init_db()

    cfg_data = _load("geo_coherence_configs.json")
    configs  = [
        c for c in cfg_data["configs"]
        if c["preferences"]["destination"] == destination
    ]
    if not configs:
        print(f"No coherence configs found for destination '{destination}'.")
        print("Available destinations in geo_coherence_configs.json:")
        dests = set(c["preferences"]["destination"] for c in cfg_data["configs"])
        for d in dests:
            print(f"  - {d}")
        return {}

    print(f"\n{'='*60}")
    print(f"PHASE 2.7  Geographic Coherence — {destination}")
    print(f"{'='*60}")
    print(f"  {len(configs)} configs loaded.")

    venues = get_venues_by_destination(destination)
    if not venues:
        print(f"\n  ✗ No cached venues for '{destination}'.")
        print(f"  Run: python -m src.ingestion.overpass --destination \"{destination}\"")
        return {}

    embed_and_cache(destination)
    venues = get_venues_by_destination(destination)

    all_day_averages: list[float] = []
    itinerary_results: list[dict] = []

    for cfg in configs:
        prefs = cfg["preferences"]
        print(f"\n  [{cfg['id']}] {cfg['label']}")

        matched  = match_venues(venues, prefs)
        clusters = cluster_venues(matched, prefs["days"])

        try:
            itinerary = build_itinerary(clusters, prefs)
        except Exception as exc:
            print(f"    ✗ Generation failed: {exc}")
            continue

        venue_lookup = {v["osm_id"]: v for c in clusters for v in c}
        annotate_itinerary_travel_times(itinerary, venue_lookup)

        day_avgs: list[float] = []
        for day in itinerary:
            legs = [
                slot["travel_to_next"]["duration_min"]
                for slot in day.get("slots", [])
                if slot.get("travel_to_next")
            ]
            if legs:
                avg = sum(legs) / len(legs)
                day_avgs.append(avg)
                all_day_averages.append(avg)
                print(f"    Day {day['day_number']}: {len(legs)} legs, avg {avg:.1f} min")

        itinerary_results.append({
            "id": cfg["id"], "label": cfg["label"],
            "day_averages_min": [round(a, 1) for a in day_avgs],
            "itinerary_avg_min": round(sum(day_avgs)/len(day_avgs), 1) if day_avgs else None,
        })

        time.sleep(0.5)   # rate-limit between Groq calls

    # Aggregate
    if all_day_averages:
        sorted_avgs = sorted(all_day_averages)
        n           = len(sorted_avgs)
        median      = sorted_avgs[n // 2] if n % 2 else (sorted_avgs[n//2 - 1] + sorted_avgs[n//2]) / 2
        mean        = sum(all_day_averages) / n
        target_ok   = median < 20.0

        print(f"\n{'─'*60}")
        print(f"COHERENCE SUMMARY  ({n} day-groups across {len(itinerary_results)} itineraries)")
        print(f"{'─'*60}")
        print(f"  Median intra-day avg transit : {median:.1f} min")
        print(f"  Mean intra-day avg transit   : {mean:.1f} min")
        print(f"  Min / Max                    : {min(all_day_averages):.1f} / {max(all_day_averages):.1f} min")
        print(f"  Target < 20 min median       : {'✓ PASS' if target_ok else '✗ FAIL'}")
    else:
        median, mean = None, None
        target_ok    = False

    result = {
        "task": "coherence", "destination": destination,
        "n_itineraries": len(itinerary_results),
        "n_day_groups": len(all_day_averages),
        "median_intraday_avg_min": round(median, 1) if median else None,
        "mean_intraday_avg_min":   round(mean, 1)   if mean   else None,
        "target_pass": target_ok,
        "itineraries": itinerary_results,
    }
    safe_dest = destination.replace(" ", "_").replace(",", "")
    _save(f"coherence_results_{safe_dest}.json", result)
    return result


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Travel-agent evaluation runner")
    parser.add_argument(
        "--task",
        choices=["extraction", "rubric", "coherence", "all"],
        default="all",
    )
    parser.add_argument(
        "--destination",
        default="Manhattan, New York",
        help="Destination for coherence eval (must be pre-cached)",
    )
    args = parser.parse_args()

    if args.task in ("extraction", "all"):
        run_extraction_eval()

    if args.task in ("rubric", "all"):
        run_rubric_eval()

    if args.task in ("coherence", "all"):
        run_coherence_eval(args.destination)

    print("\nDone. Results saved to eval/results/")


if __name__ == "__main__":
    main()
