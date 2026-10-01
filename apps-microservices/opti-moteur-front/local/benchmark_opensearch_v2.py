#!/usr/bin/env python3
"""
Benchmark OpenSearch avec DETECTION CATEGORIE + FILTER (prefix-match).
Reprend le bench precedent + ajoute os_hybrid_v2 (equivalent TS).

Strategy os_hybrid_v2:
  1. Aggregation terms sur categorie + un match sur la query -> top categories
  2. Prefix-match check (idem Typesense)
  3. Si valid categories -> bool.must avec filter term on categorie
  4. Query BM25 + kNN dans bool.should
"""
import json
import os
import re
import sys
import time
import unicodedata
import requests

OS_HOST = os.getenv("OS_HOST", "http://localhost:9200")
OS_INDEX = os.getenv("OS_INDEX", "produits_hellopro_cam")
QUERY_FILE = "data/query_embeddings.json"
TOP_K = 10
TOP_CATS_FACET = 3


def normalize(s):
    if not s: return ""
    s = unicodedata.normalize("NFD", s)
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower()


def tokenize(s):
    return set(re.findall(r"[a-z0-9]{2,}", normalize(s)))


def tokenize_ordered(s):
    return re.findall(r"[a-z0-9]{2,}", normalize(s))


def is_prefix_match(q_tokens, cat_name, lookahead=2):
    toks = tokenize_ordered(cat_name)
    return q_tokens.issubset(set(toks[: len(q_tokens) + lookahead]))


def os_search(body, timeout=30):
    t = time.time()
    r = requests.post(f"{OS_HOST}/{OS_INDEX}/_search", json=body, timeout=timeout)
    r.raise_for_status()
    return r.json(), (time.time() - t) * 1000


def extract_hits(res, top_k=TOP_K):
    hits = res.get("hits", {}).get("hits", [])
    out = []
    for h in hits[:top_k]:
        src = h.get("_source", {})
        out.append({
            "id_produit": src.get("id_produit"),
            "nom": src.get("nom_produit") or "",
            "categorie": src.get("categorie") or "",
            "score": round(h.get("_score", 0), 3),
        })
    return out


def detect_categories_os(query):
    """
    Aggregation terms : quelles categories matchent le plus la query sur le champ categorie.
    Retourne les top_n_cats qui passent le prefix-match test.
    """
    body = {
        "size": 0,
        "query": {
            "multi_match": {
                "query": query,
                "fields": ["categorie^3"],
                "fuzziness": "AUTO",
            }
        },
        "aggs": {
            "top_cats": {
                "terms": {"field": "categorie", "size": TOP_CATS_FACET}
            }
        },
    }
    try:
        res, _ = os_search(body)
    except Exception:
        return []
    buckets = res.get("aggregations", {}).get("top_cats", {}).get("buckets", [])
    q_tokens = tokenize(query)
    valid = [b["key"] for b in buckets if is_prefix_match(q_tokens, b["key"])]
    return valid


def search_hybrid_v2(query, vec):
    """Hybrid + filter_by categorie (prefix-match only)."""
    valid_cats = detect_categories_os(query)

    must_filter = []
    if valid_cats:
        must_filter.append({"terms": {"categorie": valid_cats}})

    body = {
        "size": TOP_K * 3,
        "_source": ["id_produit", "nom_produit", "categorie"],
        "query": {
            "bool": {
                "must": must_filter,
                "should": [
                    {
                        "multi_match": {
                            "query": query,
                            "fields": ["nom_produit^5", "categorie^10", "text"],
                            "type": "best_fields",
                            "fuzziness": "AUTO",
                            "boost": 0.5,
                        }
                    },
                    {
                        "knn": {
                            "embedding": {"vector": vec, "k": 100, "boost": 0.5}
                        }
                    },
                ],
                "minimum_should_match": 1,
            }
        },
        "collapse": {"field": "id_produit"},
    }
    res, lat = os_search(body)
    return extract_hits(res), lat, valid_cats


def main():
    try:
        r = requests.get(f"{OS_HOST}/_cluster/health", timeout=5)
        r.raise_for_status()
        print(f"[OK] OpenSearch: {r.json()['status']}")
    except Exception as e:
        print(f"[ERREUR] OpenSearch injoignable: {e}")
        sys.exit(1)

    with open(QUERY_FILE, "r", encoding="utf-8") as f:
        queries_data = json.load(f)
    print(f"[OK] {len(queries_data)} requetes")

    # Reload existing bench_opensearch.json pour garder bm25, knn, hybrid
    try:
        with open("bench_opensearch.json", "r", encoding="utf-8") as f:
            existing = {r["query"]: r for r in json.load(f)}
    except FileNotFoundError:
        existing = {}

    results = []
    for i, item in enumerate(queries_data, 1):
        q, vec = item["text"], item["vector"]
        print(f"  [{i}/{len(queries_data)}] {q!r} ...", end=" ", flush=True)

        hits_v2, lat_v2, valid_cats = search_hybrid_v2(q, vec)

        record = existing.get(q, {"query": q})
        record["os_hybrid_v2"] = {"hits": hits_v2, "lat_ms": round(lat_v2), "filter_cats": valid_cats}
        results.append(record)
        cat_txt = f"({', '.join(valid_cats)[:40]})" if valid_cats else "(no filter)"
        print(f"v2={lat_v2:.0f}ms {cat_txt}")

    with open("bench_opensearch.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    n = len(results)
    avg = lambda k: sum(r[k]["lat_ms"] for r in results if k in r) / max(len([r for r in results if k in r]), 1)
    print(f"\n{'='*50}")
    print(f"  LATENCES (n={n})")
    print(f"{'='*50}")
    for k in ("os_bm25", "os_knn", "os_hybrid", "os_hybrid_v2"):
        if any(k in r for r in results):
            print(f"  {k:<15s}: {avg(k):>6.0f} ms")


if __name__ == "__main__":
    main()
