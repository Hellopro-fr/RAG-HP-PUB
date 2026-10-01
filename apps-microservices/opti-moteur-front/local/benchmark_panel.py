#!/usr/bin/env python3
"""
Benchmark panel : pour chaque requete pre-embeddee, compare 3 modes :
  1. SEMANTIQUE PUR    (simule Milvus actuel)
  2. BM25 PUR          (keyword only)
  3. HYBRID TYPESENSE  (BM25 + vecteur + re-rank Python, la solution proposee)

Produit:
  - bench_results.json   (donnees brutes)
  - bench_report.html    (rapport visuel side-by-side)
"""
import json
import os
import re
import sys
import time
import unicodedata
import requests
import typesense

TS_HOST = os.getenv("TS_HOST", "localhost")
TS_PORT = os.getenv("TS_PORT", "8108")
TS_KEY = os.getenv("TS_API_KEY", "hp_poc_2026")
TS_COLLECTION = os.getenv("TS_COLLECTION", "produits_30k")
QUERY_FILE = "data/query_embeddings.json"
TOP_K = 10
CANDIDATES = 50

# Poids du re-rank Python
W_VECTOR, W_BM25, W_NAME, W_CAT = 0.55, 0.10, 0.25, 0.10
CAT_FILTER_THRESHOLD = 0.80
CAT_FILTER_TOP_N = 3

client = typesense.Client({
    "api_key": TS_KEY,
    "nodes": [{"host": TS_HOST, "port": TS_PORT, "protocol": "http"}],
    "connection_timeout_seconds": 60,
})


def normalize(s):
    if not s: return ""
    s = unicodedata.normalize("NFD", s)
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower()


def tokenize(s):
    return set(re.findall(r"[a-z0-9]{2,}", normalize(s)))


def tokenize_ordered(s):
    return re.findall(r"[a-z0-9]{2,}", normalize(s))


def is_prefix_match(q_tokens, cat_name, lookahead=2):
    """Prefix-match tolerant singulier/pluriel via startswith bilateral."""
    prefix_toks = tokenize_ordered(cat_name)[: len(q_tokens) + lookahead]
    def matches(q):
        for ct in prefix_toks:
            if ct == q: return True
            if len(q) >= 4 and len(ct) >= 4 and (ct.startswith(q) or q.startswith(ct)):
                return True
        return False
    return all(matches(q) for q in q_tokens)


def ts_multi(params):
    body = {"searches": [{"collection": TS_COLLECTION, **params}]}
    return client.multi_search.perform(body, {})["results"][0]


def detect_cats(query):
    """Retourne (top_cat_name, confidence, valid_cats_prefix_match)"""
    params = {"q": query, "query_by": "categorie", "per_page": 1,
              "facet_by": "categorie", "max_facet_values": CAT_FILTER_TOP_N,
              "typo_tokens_threshold": 2}
    try:
        res = ts_multi(params)
    except Exception:
        return None, 0, []
    facets = res.get("facet_counts", [])
    if not facets:
        return None, 0, []
    counts = facets[0].get("counts", [])
    if not counts:
        return None, 0, []
    total = sum(c["count"] for c in counts) or 1
    top_cats = [c["value"] for c in counts]
    q_tokens = tokenize(query)
    valid = [c for c in top_cats if is_prefix_match(q_tokens, c)]
    confidence = counts[0]["count"] / total
    return counts[0]["value"], confidence, valid


# ---------- 3 methodes de recherche ----------
def search_semantic(query, vec):
    vec_str = json.dumps(vec)
    params = {"q": "*", "vector_query": f"embedding:({vec_str}, k:{CANDIDATES})",
              "per_page": TOP_K, "group_by": "id_produit", "group_limit": 1}
    t = time.time()
    res = ts_multi(params)
    return _extract_hits(res), (time.time() - t) * 1000


def search_bm25(query):
    params = {"q": query, "query_by": "nom_produit,categorie,text",
              "query_by_weights": "5,10,1", "per_page": TOP_K,
              "group_by": "id_produit", "group_limit": 1,
              "typo_tokens_threshold": 3, "drop_tokens_threshold": 2}
    t = time.time()
    res = ts_multi(params)
    return _extract_hits(res), (time.time() - t) * 1000


def search_hybrid(query, vec, filter_cats=None):
    vec_str = json.dumps(vec)
    params = {"q": query, "query_by": "nom_produit,categorie,text",
              "query_by_weights": "5,10,1",
              "vector_query": f"embedding:({vec_str}, k:{CANDIDATES})",
              "per_page": CANDIDATES, "group_by": "id_produit", "group_limit": 1,
              "typo_tokens_threshold": 3, "drop_tokens_threshold": 2}
    if filter_cats:
        escaped = ",".join(f"`{c}`" for c in filter_cats)
        params["filter_by"] = f"categorie:=[{escaped}]"
    t = time.time()
    res = ts_multi(params)
    # Re-rank Python
    groups = res.get("grouped_hits", [])
    q_tokens = tokenize(query)
    raw = []
    for g in groups:
        hits = g.get("hits", [])
        if not hits: continue
        hit = hits[0]
        doc = hit["document"]
        vec_dist = hit.get("vector_distance")
        vec_score = 1 - min(vec_dist or 1.0, 1.0)
        tm = hit.get("text_match", 0) or 0
        name_match = len(q_tokens & tokenize(doc.get("nom_produit", ""))) / max(len(q_tokens), 1)
        cat_match = len(q_tokens & tokenize(doc.get("categorie", ""))) / max(len(q_tokens), 1)
        raw.append({"doc": doc, "vec": vec_score, "tm_raw": tm,
                    "name_m": name_match, "cat_m": cat_match})
    max_tm = max((r["tm_raw"] for r in raw), default=0) or 1
    for r in raw:
        r["tm"] = r["tm_raw"] / max_tm if max_tm > 0 else 0
        r["score"] = W_VECTOR*r["vec"] + W_BM25*r["tm"] + W_NAME*r["name_m"] + W_CAT*r["cat_m"]
        if r["vec"] < 0.20 and r["name_m"] < 0.50:
            r["score"] *= 0.3
    raw.sort(key=lambda x: -x["score"])
    hits_out = [{"id_produit": r["doc"].get("id_produit"),
                 "nom": r["doc"].get("nom_produit") or "",
                 "categorie": r["doc"].get("categorie") or "",
                 "score": round(r["score"], 3)} for r in raw[:TOP_K]]
    return hits_out, (time.time() - t) * 1000


def _extract_hits(res):
    groups = res.get("grouped_hits", [])
    out = []
    for g in groups[:TOP_K]:
        hits = g.get("hits", [])
        if not hits: continue
        doc = hits[0]["document"]
        out.append({"id_produit": doc.get("id_produit"),
                    "nom": doc.get("nom_produit") or "",
                    "categorie": doc.get("categorie") or "",
                    "score": 0})
    return out


# ---------- MAIN ----------
def main():
    # Healthcheck
    try:
        requests.get(f"http://{TS_HOST}:{TS_PORT}/health", timeout=3).raise_for_status()
    except Exception as e:
        print(f"[ERREUR] Typesense injoignable: {e}")
        sys.exit(1)

    with open(QUERY_FILE, "r", encoding="utf-8") as f:
        queries_data = json.load(f)
    print(f"[OK] {len(queries_data)} requetes chargees")

    results = []
    for i, item in enumerate(queries_data, 1):
        q, vec = item["text"], item["vector"]
        print(f"  [{i}/{len(queries_data)}] {q!r} ...", end=" ")

        # 1. Semantique pur
        sem_hits, sem_lat = search_semantic(q, vec)
        # 2. BM25 pur
        bm_hits, bm_lat = search_bm25(q)
        # 3. Hybrid v2
        top_cat, conf, valid_cats = detect_cats(q)
        filter_cats = valid_cats if conf >= CAT_FILTER_THRESHOLD and valid_cats else None
        hyb_hits, hyb_lat = search_hybrid(q, vec, filter_cats=filter_cats)

        results.append({
            "query": q, "n_tokens": len(q.split()),
            "detected_cat": top_cat, "confidence": round(conf, 2),
            "filter_applied": filter_cats,
            "semantic": {"hits": sem_hits, "lat_ms": round(sem_lat)},
            "bm25":     {"hits": bm_hits,  "lat_ms": round(bm_lat)},
            "hybrid":   {"hits": hyb_hits, "lat_ms": round(hyb_lat)},
        })
        print(f"sem={sem_lat:.0f}ms bm25={bm_lat:.0f}ms hyb={hyb_lat:.0f}ms")

    # Sauvegarde JSON
    with open("bench_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n[OK] bench_results.json sauvegarde")

    # Metriques globales
    n = len(results)
    avg_sem = sum(r["semantic"]["lat_ms"] for r in results) / n
    avg_bm = sum(r["bm25"]["lat_ms"] for r in results) / n
    avg_hyb = sum(r["hybrid"]["lat_ms"] for r in results) / n
    print(f"\n{'='*50}")
    print(f"  LATENCES MOYENNES (n={n})")
    print(f"{'='*50}")
    print(f"  Semantique pur : {avg_sem:>6.0f} ms")
    print(f"  BM25 pur       : {avg_bm:>6.0f} ms")
    print(f"  Hybrid Typesense: {avg_hyb:>6.0f} ms")


if __name__ == "__main__":
    main()
