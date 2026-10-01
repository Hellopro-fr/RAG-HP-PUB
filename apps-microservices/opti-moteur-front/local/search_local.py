#!/usr/bin/env python3
"""
Benchmark Typesense local sur la collection produits_20k (issue de Milvus prod).
Version Windows sans baseline Milvus (prod non accessible depuis le poste).

Usage:
    python search_local.py                       # 4 requetes par defaut
    python search_local.py "armoire medicale"    # une requete specifique
"""

import json
import os
import sys
import time
import requests
import typesense

TS_HOST = os.getenv("TS_HOST", "localhost")
TS_PORT = os.getenv("TS_PORT", "8108")
TS_KEY = os.getenv("TS_API_KEY", "hp_poc_2026")
TS_COLLECTION = os.getenv("TS_COLLECTION", "produits_20k")
QUERY_EMB_FILE = "data/query_embeddings.json"
TOP_K = 10

client = typesense.Client({
    "api_key": TS_KEY,
    "nodes": [{"host": TS_HOST, "port": TS_PORT, "protocol": "http"}],
    "connection_timeout_seconds": 60,
})


def load_query_embeddings():
    if not os.path.exists(QUERY_EMB_FILE):
        print(f"[ERREUR] {QUERY_EMB_FILE} introuvable")
        sys.exit(1)
    with open(QUERY_EMB_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {item["text"]: item["vector"] for item in data}


def ts(params):
    body = {"searches": [{"collection": TS_COLLECTION, **params}]}
    return client.multi_search.perform(body, {})["results"][0]


def ts_semantic(vec):
    vec_str = json.dumps(vec)
    params = {
        "q": "*",
        "vector_query": f"embedding:({vec_str}, k:200)",
        "per_page": TOP_K,
        "group_by": "id_produit",
        "group_limit": 1,
    }
    t = time.time()
    res = ts(params)
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
    res = ts(params)
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
    res = ts(params)
    return res, (time.time() - t) * 1000, weights


def display(res, lat, label):
    groups = res.get("grouped_hits", [])
    print(f"\n{'-'*92}")
    print(f"  {label}  |  {lat:.0f}ms  |  {len(groups)} produits")
    print(f"{'-'*92}")
    for i, g in enumerate(groups[:TOP_K], 1):
        d = g["hits"][0]["document"]
        nom = (d.get("nom_produit") or d.get("text", ""))[:62]
        cat = (d.get("categorie") or "?")[:30]
        print(f"  #{i:2d}  [{d['id_produit']:>10}]  {nom:<64}  | {cat}")


def bench(query, query_vecs):
    vec = query_vecs.get(query)
    if not vec:
        print(f"[ERREUR] Pas de vecteur pre-calcule pour '{query}'")
        print(f"         Dispos: {sorted(query_vecs.keys())}")
        return

    print(f"\n{'='*92}")
    print(f"  REQUETE: \"{query}\"  ({len(query.split())} mots)")
    print(f"{'='*92}")

    r1, l1 = ts_semantic(vec)
    display(r1, l1, "SEMANTIQUE PUR (simule Milvus)")

    r2, l2 = ts_bm25(query)
    display(r2, l2, "BM25 PUR")

    r3, l3, w = ts_hybrid(query, vec)
    display(r3, l3, f"HYBRID (weights={w})")

    print(f"\n  Latences : semantique={l1:.0f}ms | BM25={l2:.0f}ms | hybrid={l3:.0f}ms")


def main():
    try:
        requests.get(f"http://{TS_HOST}:{TS_PORT}/health", timeout=3).raise_for_status()
    except Exception as e:
        print(f"[ERREUR] Typesense injoignable: {e}")
        sys.exit(1)

    info = client.collections[TS_COLLECTION].retrieve()
    print(f"[OK] Collection '{TS_COLLECTION}' : {info['num_documents']} docs")

    query_vecs = load_query_embeddings()
    print(f"[OK] {len(query_vecs)} requetes pre-embeddees")

    queries = sys.argv[1:] if len(sys.argv) > 1 else [
        "armoire medicale",
        "armoire médicale",
        "pompe hydraulique",
        "batterie lithium",
    ]
    for q in queries:
        bench(q, query_vecs)


if __name__ == "__main__":
    main()
