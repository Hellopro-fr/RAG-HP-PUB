#!/usr/bin/env python3
"""
Benchmark OpenSearch 3 modes sur les 26 requetes pre-embeddees :
  1. BM25 seul (multi_match avec analyzer francais)
  2. kNN pur (vectoriel seul)
  3. Hybrid (kNN + BM25 via bool query)

Produit bench_opensearch.json a merger avec bench_results.json (Typesense).
"""
import json
import os
import sys
import time
import requests

OS_HOST = os.getenv("OS_HOST", "http://localhost:9200")
OS_INDEX = os.getenv("OS_INDEX", "produits_hellopro_cam")
QUERY_FILE = "data/query_embeddings.json"
TOP_K = 10


def os_search(body, timeout=30):
    t = time.time()
    r = requests.post(f"{OS_HOST}/{OS_INDEX}/_search", json=body, timeout=timeout)
    r.raise_for_status()
    res = r.json()
    return res, (time.time() - t) * 1000


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


def search_bm25(query):
    body = {
        "size": TOP_K * 2,  # on fetch plus puis on collapse
        "_source": ["id_produit", "nom_produit", "categorie"],
        "query": {
            "multi_match": {
                "query": query,
                "fields": ["nom_produit^5", "categorie^10", "text"],
                "type": "best_fields",
                "fuzziness": "AUTO",
            }
        },
        "collapse": {"field": "id_produit"},
    }
    res, lat = os_search(body)
    return extract_hits(res), lat


def search_knn(vec):
    """Vectoriel pur - simulation 'Milvus-like'."""
    body = {
        "size": TOP_K * 3,
        "_source": ["id_produit", "nom_produit", "categorie"],
        "query": {
            "knn": {"embedding": {"vector": vec, "k": 100}}
        },
        "collapse": {"field": "id_produit"},
    }
    res, lat = os_search(body)
    return extract_hits(res), lat


def search_hybrid(query, vec):
    """
    Hybrid OpenSearch : combine BM25 + kNN via bool.should (somme des scores).
    Note : OpenSearch 2.x propose aussi 'hybrid' pipeline, mais bool.should est
    plus simple et fonctionne sans installation de pipeline.
    """
    body = {
        "size": TOP_K * 3,
        "_source": ["id_produit", "nom_produit", "categorie"],
        "query": {
            "bool": {
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
                ]
            }
        },
        "collapse": {"field": "id_produit"},
    }
    res, lat = os_search(body)
    return extract_hits(res), lat


def main():
    # Healthcheck
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

    results = []
    for i, item in enumerate(queries_data, 1):
        q, vec = item["text"], item["vector"]
        print(f"  [{i}/{len(queries_data)}] {q!r} ...", end=" ", flush=True)

        try:
            bm_hits, bm_lat = search_bm25(q)
        except Exception as e:
            print(f"BM25 err={e}"); continue
        try:
            knn_hits, knn_lat = search_knn(vec)
        except Exception as e:
            print(f"kNN err={e}"); continue
        try:
            hyb_hits, hyb_lat = search_hybrid(q, vec)
        except Exception as e:
            print(f"hybrid err={e}"); continue

        results.append({
            "query": q,
            "os_bm25":   {"hits": bm_hits,  "lat_ms": round(bm_lat)},
            "os_knn":    {"hits": knn_hits, "lat_ms": round(knn_lat)},
            "os_hybrid": {"hits": hyb_hits, "lat_ms": round(hyb_lat)},
        })
        print(f"bm25={bm_lat:.0f}ms knn={knn_lat:.0f}ms hyb={hyb_lat:.0f}ms")

    with open("bench_opensearch.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    n = len(results)
    avg = lambda k: sum(r[k]["lat_ms"] for r in results) / n if n else 0
    print(f"\n{'='*50}")
    print(f"  OPENSEARCH LATENCES MOYENNES (n={n})")
    print(f"{'='*50}")
    print(f"  BM25 pur     : {avg('os_bm25'):>6.0f} ms")
    print(f"  kNN pur      : {avg('os_knn'):>6.0f} ms")
    print(f"  Hybrid       : {avg('os_hybrid'):>6.0f} ms")
    print(f"\n[OK] bench_opensearch.json sauvegarde")


if __name__ == "__main__":
    main()
