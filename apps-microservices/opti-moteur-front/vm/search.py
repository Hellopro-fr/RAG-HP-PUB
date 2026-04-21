#!/usr/bin/env python3
"""
Benchmark Typesense (produits_200k) vs Milvus prod (produits_3)
sur les memes requetes de test, avec group_by id_produit pour dedoublonner les chunks.

Utilise les requetes pre-embeddees dans data/query_embeddings.json
(copier depuis le POC Windows: C:\\RIJA\\CLAUDE_CODE\\poc_typesense\\data\\query_embeddings.json)

Usage:
    python3 search.py
    # ou pour une requete specifique :
    python3 search.py "armoire medicale"
"""

import json
import os
import sys
import time
import requests
import typesense
from pymilvus import connections, Collection

# =============================================================================
# CONFIG
# =============================================================================
TS_HOST = os.getenv("TS_HOST", "localhost")
TS_PORT = os.getenv("TS_PORT", "8108")
TS_KEY = os.getenv("TS_API_KEY", "hp_poc_2026")
TS_COLLECTION = os.getenv("TS_COLLECTION", "produits_200k")

MILVUS_HOST = os.getenv("MILVUS_HOST", "milvus-prod.hello.dev.private.com")
MILVUS_PORT = os.getenv("MILVUS_PORT", "19530")
MILVUS_COLLECTION = os.getenv("MILVUS_COLLECTION", "produits_3")

QUERY_EMB_FILE = os.getenv("QUERY_EMB", "data/query_embeddings.json")
TOP_K = 10

client = typesense.Client({
    "api_key": TS_KEY,
    "nodes": [{"host": TS_HOST, "port": TS_PORT, "protocol": "http"}],
    "connection_timeout_seconds": 60,
})


# =============================================================================
# HELPERS
# =============================================================================
def load_query_embeddings():
    if not os.path.exists(QUERY_EMB_FILE):
        print(f"[ERREUR] {QUERY_EMB_FILE} introuvable.")
        print("        Copier depuis : C:\\RIJA\\CLAUDE_CODE\\poc_typesense\\data\\query_embeddings.json")
        sys.exit(1)
    with open(QUERY_EMB_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {item["text"]: item["vector"] for item in data}


def ts_multi_search(params):
    body = {"searches": [{"collection": TS_COLLECTION, **params}]}
    res = client.multi_search.perform(body, {})
    return res["results"][0]


# =============================================================================
# SEARCH - TYPESENSE
# =============================================================================
def ts_semantic(query, vec):
    """Vectoriel pur. group_by pour dedoublonner les chunks."""
    vec_str = json.dumps(vec)
    params = {
        "q": "*",
        "vector_query": f"embedding:({vec_str}, k:200)",
        "per_page": TOP_K,
        "group_by": "id_produit",
        "group_limit": 1,
    }
    t = time.time()
    res = ts_multi_search(params)
    return res, (time.time() - t) * 1000


def ts_bm25(query):
    params = {
        "q": query,
        "query_by": "nom_produit,text",
        "query_by_weights": "5,1",
        "per_page": TOP_K,
        "group_by": "id_produit",
        "group_limit": 1,
        "typo_tokens_threshold": 3,
        "drop_tokens_threshold": 2,
    }
    t = time.time()
    res = ts_multi_search(params)
    return res, (time.time() - t) * 1000


def ts_hybrid(query, vec):
    vec_str = json.dumps(vec)
    n = len(query.split())
    weights = "7,1" if n <= 2 else ("5,1" if n <= 4 else "3,1")
    params = {
        "q": query,
        "query_by": "nom_produit,text",
        "query_by_weights": weights,
        "vector_query": f"embedding:({vec_str}, k:200)",
        "per_page": TOP_K,
        "group_by": "id_produit",
        "group_limit": 1,
        "typo_tokens_threshold": 3,
        "drop_tokens_threshold": 2,
    }
    t = time.time()
    res = ts_multi_search(params)
    return res, (time.time() - t) * 1000, weights


# =============================================================================
# SEARCH - MILVUS (baseline prod)
# =============================================================================
_milvus_col = None


def milvus_connect():
    global _milvus_col
    if _milvus_col is not None:
        return _milvus_col
    print(f"[INFO] Connexion Milvus {MILVUS_HOST}:{MILVUS_PORT}")
    connections.connect(alias="default", host=MILVUS_HOST, port=MILVUS_PORT)
    _milvus_col = Collection(MILVUS_COLLECTION)
    _milvus_col.load()
    return _milvus_col


def milvus_semantic(vec):
    col = milvus_connect()
    t = time.time()
    res = col.search(
        data=[vec],
        anns_field="embedding",
        param={"metric_type": "IP", "params": {"ef": 64}},
        limit=TOP_K * 5,  # sur-echantillonne pour dedup id_produit
        output_fields=["id_produit", "nom_produit", "categorie", "fournisseur", "chunk_number"],
    )
    latency = (time.time() - t) * 1000
    # Dedup par id_produit
    seen, hits = set(), []
    for hit in res[0]:
        pid = hit.entity.get("id_produit")
        if pid in seen:
            continue
        seen.add(pid)
        hits.append({
            "id_produit": pid,
            "nom_produit": hit.entity.get("nom_produit"),
            "categorie": hit.entity.get("categorie"),
            "fournisseur": hit.entity.get("fournisseur"),
            "score": hit.distance,
        })
        if len(hits) >= TOP_K:
            break
    return hits, latency


# =============================================================================
# DISPLAY
# =============================================================================
def display_ts(res, latency_ms, label):
    groups = res.get("grouped_hits", [])
    print(f"\n{'-'*90}")
    print(f"  {label}  |  {latency_ms:.0f}ms  |  {len(groups)} produits uniques")
    print(f"{'-'*90}")
    for i, g in enumerate(groups[:TOP_K], 1):
        doc = g["hits"][0]["document"]
        nom = (doc.get("nom_produit") or doc.get("text", ""))[:60]
        cat = doc.get("categorie", "?")[:30]
        print(f"  #{i:2d}  [{doc['id_produit']:>10}]  {nom:<62}  | {cat}")


def display_milvus(hits, latency_ms, label="MILVUS PROD (baseline)"):
    print(f"\n{'-'*90}")
    print(f"  {label}  |  {latency_ms:.0f}ms  |  {len(hits)} produits uniques")
    print(f"{'-'*90}")
    for i, h in enumerate(hits[:TOP_K], 1):
        nom = (h.get("nom_produit") or "")[:60]
        cat = (h.get("categorie") or "?")[:30]
        print(f"  #{i:2d}  [{h['id_produit']:>10}]  {nom:<62}  | {cat}")


# =============================================================================
# BENCHMARK
# =============================================================================
def bench(query, query_vecs, include_milvus=True):
    vec = query_vecs.get(query)
    if not vec:
        print(f"[ERREUR] Pas de vecteur pre-calcule pour '{query}'.")
        print(f"         Disponibles : {sorted(query_vecs.keys())}")
        return

    print(f"\n{'='*90}")
    print(f"  REQUETE: \"{query}\"  ({len(query.split())} mots)")
    print(f"{'='*90}")

    r1, l1 = ts_semantic(query, vec)
    display_ts(r1, l1, "TS | SEMANTIQUE PUR")

    r2, l2 = ts_bm25(query)
    display_ts(r2, l2, "TS | BM25 PUR")

    r3, l3, w = ts_hybrid(query, vec)
    display_ts(r3, l3, f"TS | HYBRID (weights={w})")

    if include_milvus:
        try:
            r4, l4 = milvus_semantic(vec)
            display_milvus(r4, l4)
        except Exception as e:
            print(f"[WARN] Milvus baseline indisponible: {e}")

    print(f"\n{'='*90}")
    print(f"  RESUME  \"{query}\"")
    print(f"{'='*90}")
    summary = [("TS Semantique", l1), ("TS BM25", l2), ("TS Hybrid", l3)]
    if include_milvus:
        try:
            summary.append(("MILVUS baseline", l4))
        except NameError:
            pass
    for name, lat in summary:
        print(f"  {name:<24s}  {lat:>8.0f} ms")


def main():
    # Healthcheck
    try:
        requests.get(f"http://{TS_HOST}:{TS_PORT}/health", timeout=3).raise_for_status()
    except Exception as e:
        print(f"[ERREUR] Typesense injoignable: {e}")
        sys.exit(1)

    query_vecs = load_query_embeddings()
    print(f"[OK] {len(query_vecs)} requetes pre-embeddees chargees")

    queries_to_test = sys.argv[1:] if len(sys.argv) > 1 else [
        "armoire medicale",
        "armoire médicale",
        "pompe hydraulique",
        "armoire sécurité inflammables",
    ]

    for q in queries_to_test:
        bench(q, query_vecs, include_milvus=True)

    # Cleanup
    try:
        connections.disconnect("default")
    except Exception:
        pass


if __name__ == "__main__":
    main()
