#!/usr/bin/env python3
"""
Calcule P@5 et P@10 pour tous les modes a partir du ground truth.
Fusionne bench_results.json (TS) + bench_opensearch.json (OS) + data/ground_truth.json.
Produit bench_metrics.json.
"""
import json


def load():
    with open("bench_results.json", "r", encoding="utf-8") as f:
        ts = json.load(f)
    with open("bench_opensearch.json", "r", encoding="utf-8") as f:
        os_r = json.load(f)
    with open("data/ground_truth.json", "r", encoding="utf-8") as f:
        gt = json.load(f)["ground_truth"]
    return ts, os_r, gt


def is_relevant(categorie, gt_entry):
    """Check si une categorie correspond au ground truth."""
    if not categorie:
        return False
    accept = set(gt_entry.get("accept", []))
    if categorie in accept:
        return True
    for prefix in gt_entry.get("prefix", []):
        if categorie.startswith(prefix):
            return True
    return False


def precision_at_k(hits, gt_entry, k):
    if not hits: return 0.0
    top_k = hits[:k]
    n = min(len(top_k), k)
    if n == 0: return 0.0
    relevant = sum(1 for h in top_k if is_relevant(h.get("categorie", ""), gt_entry))
    return relevant / n


def main():
    ts, os_r, gt = load()
    gt_by_q = {g["query"]: g for g in gt}
    os_by_q = {r["query"]: r for r in os_r}

    metrics = []
    for ts_rec in ts:
        q = ts_rec["query"]
        gt_entry = gt_by_q.get(q)
        if not gt_entry:
            print(f"[WARN] Pas de ground truth pour '{q}'")
            continue

        os_rec = os_by_q.get(q, {})

        # Collect all modes
        modes = {}
        for mode_name, rec, latency_key in [
            ("ts_semantic", ts_rec["semantic"], "lat_ms"),
            ("ts_bm25",     ts_rec["bm25"],     "lat_ms"),
            ("ts_hybrid",   ts_rec["hybrid"],   "lat_ms"),
            ("os_bm25",     os_rec.get("os_bm25", {}),     "lat_ms"),
            ("os_knn",      os_rec.get("os_knn", {}),      "lat_ms"),
            ("os_hybrid",   os_rec.get("os_hybrid", {}),   "lat_ms"),
            ("os_hybrid_v2", os_rec.get("os_hybrid_v2", {}), "lat_ms"),
        ]:
            if not rec: continue
            hits = rec.get("hits", [])
            modes[mode_name] = {
                "p5":  round(precision_at_k(hits, gt_entry, 5) * 100),
                "p10": round(precision_at_k(hits, gt_entry, 10) * 100),
                "lat_ms": rec.get(latency_key, 0),
                "hits": hits,
            }

        metrics.append({
            "query": q,
            "ground_truth": {
                "accept": gt_entry.get("accept", []),
                "prefix": gt_entry.get("prefix", []),
            },
            "detected_cat_ts": ts_rec.get("detected_cat"),
            "confidence_ts":   ts_rec.get("confidence"),
            "filter_ts":       ts_rec.get("filter_applied"),
            "filter_os_v2":    os_rec.get("os_hybrid_v2", {}).get("filter_cats"),
            "modes": modes,
        })

    # Resume global
    print(f"\n{'='*80}")
    print(f"{'Methode':<18s} {'P@5 moy':>10s} {'P@10 moy':>10s} {'Lat moy':>10s}")
    print('-' * 52)
    all_modes = set()
    for m in metrics:
        all_modes.update(m["modes"].keys())
    for mode in ["ts_semantic", "ts_bm25", "ts_hybrid",
                 "os_bm25", "os_knn", "os_hybrid", "os_hybrid_v2"]:
        if mode not in all_modes: continue
        p5s = [m["modes"][mode]["p5"] for m in metrics if mode in m["modes"]]
        p10s = [m["modes"][mode]["p10"] for m in metrics if mode in m["modes"]]
        lats = [m["modes"][mode]["lat_ms"] for m in metrics if mode in m["modes"]]
        avg_p5 = sum(p5s)/len(p5s) if p5s else 0
        avg_p10 = sum(p10s)/len(p10s) if p10s else 0
        avg_lat = sum(lats)/len(lats) if lats else 0
        print(f"  {mode:<16s} {avg_p5:>9.0f}% {avg_p10:>9.0f}% {avg_lat:>8.0f}ms")

    with open("bench_metrics.json", "w", encoding="utf-8") as f:
        json.dump(metrics, f, ensure_ascii=False, indent=2)
    print(f"\n[OK] bench_metrics.json genere ({len(metrics)} queries)")


if __name__ == "__main__":
    main()
