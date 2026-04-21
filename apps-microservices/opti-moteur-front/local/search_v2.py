#!/usr/bin/env python3
"""
search_v2.py - Typesense avec categorie boost + re-rank Python pondere
Objectif : < 200ms latence, pertinence top-5 maximale, zero LLM.

Ameliorations vs v1 :
  A. query_by inclut "categorie" avec fort poids -> match rubrique boost naturel
  B. detection de la categorie dominante dans la query (facet Typesense)
  C. re-rank Python sur top-50 avec formule:
       final_score = 0.50*vecteur + 0.20*bm25 + 0.20*match_nom + 0.10*match_cat
  D. affichage du detail des scores pour debug/explicabilite

Usage:
    python search_v2.py                       # 4 requetes par defaut
    python search_v2.py "armoire medicale"    # requete unique
"""

import json
import math
import os
import re
import sys
import time
import unicodedata
from collections import defaultdict

import requests
import typesense

# ============================================================
# CONFIG
# ============================================================
TS_HOST = os.getenv("TS_HOST", "localhost")
TS_PORT = os.getenv("TS_PORT", "8108")
TS_KEY = os.getenv("TS_API_KEY", "hp_poc_2026")
TS_COLLECTION = os.getenv("TS_COLLECTION", "produits_20k")
QUERY_EMB_FILE = "data/query_embeddings.json"

TOP_K = 10
CANDIDATES = 50   # nombre de candidats a rerank

# Poids du re-rank (reglables)
W_VECTOR = 0.55
W_BM25 = 0.10   # reduit : BM25 est bruyant
W_NAME = 0.25   # augmente : match exact dans le nom = signal fort
W_CAT = 0.10

# Seuil de confiance pour activer le filter_by categorie
CAT_FILTER_THRESHOLD = 0.80
# Combien de categories top-N on autorise dans le filter (en cas de rubriques adjacentes)
CAT_FILTER_TOP_N = 3

# Penalisation des resultats "bruit BM25 pur" (vec=0 et name_match faible)
PENALTY_NOISE_BM25 = True

client = typesense.Client({
    "api_key": TS_KEY,
    "nodes": [{"host": TS_HOST, "port": TS_PORT, "protocol": "http"}],
    "connection_timeout_seconds": 60,
})

# ============================================================
# HELPERS
# ============================================================
def normalize(s):
    """Strip accents + lowercase pour matching robuste."""
    if not s:
        return ""
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.lower()


def tokenize(s):
    """Split en tokens alphanumeriques normalises."""
    return set(re.findall(r"[a-z0-9]{2,}", normalize(s)))


def tokenize_ordered(s):
    """Tokens en conservant l'ordre (pour detection prefix)."""
    return re.findall(r"[a-z0-9]{2,}", normalize(s))


def is_prefix_match(query_tokens, cat_name, max_lookahead=2):
    """
    Test si tous les query_tokens apparaissent dans les PREMIERS mots du nom
    de la categorie, avec tolerance singulier/pluriel (startswith des 2 cotes).

    Exemples :
      query="batterie lithium"
      cat="Armoire de stockage batterie lithium"  -> NON (batterie en pos 4)
      cat="Batterie lithium 24V"                   -> OUI (au debut)
      cat="Batterie industrielle"                  -> NON (lithium absent)
      query="signalisation securite"
      cat="Signalisations securite travail"        -> OUI (signalisation ~ signalisations)
      query="armoire"
      cat="Armoires a pharmacie"                   -> OUI (armoire ~ armoires)
    """
    cat_toks = tokenize_ordered(cat_name)
    prefix_toks = cat_toks[: len(query_tokens) + max_lookahead]

    def matches(q_tok):
        # Match exact, ou sg/pl: l'un commence par l'autre (min 4 chars communs)
        for ct in prefix_toks:
            if ct == q_tok:
                return True
            if len(q_tok) >= 4 and len(ct) >= 4:
                if ct.startswith(q_tok) or q_tok.startswith(ct):
                    return True
        return False

    return all(matches(q) for q in query_tokens)


def load_query_embeddings():
    if not os.path.exists(QUERY_EMB_FILE):
        print(f"[ERREUR] {QUERY_EMB_FILE} introuvable")
        sys.exit(1)
    with open(QUERY_EMB_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {item["text"]: item["vector"] for item in data}


def ts_multi(params):
    body = {"searches": [{"collection": TS_COLLECTION, **params}]}
    return client.multi_search.perform(body, {})["results"][0]


# ============================================================
# A. Detection de categorie via facet search
# ============================================================
def detect_categories(query):
    """
    Cherche les top-N categories dominantes dans la query via facet Typesense.
    Retourne (top_cat, confidence, list_top_n_cats).
    """
    params = {
        "q": query,
        "query_by": "categorie",
        "per_page": 1,
        "facet_by": "categorie",
        "max_facet_values": CAT_FILTER_TOP_N,
        "typo_tokens_threshold": 2,
    }
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
    # On filtre les categories qui NE sont PAS un prefix-match
    # (evite les derives type "Armoire de stockage batterie lithium" pour "batterie lithium")
    q_tokens = tokenize(query)
    top_cats = [c["value"] for c in counts]
    valid_cats = [c for c in top_cats if is_prefix_match(q_tokens, c)]
    confidence = counts[0]["count"] / total
    # Retourne les valid_cats (ceux ou la query est bien au debut du nom)
    # Si aucun match de prefix -> pas de filter_by -> soft boost via query_by_weights
    return counts[0]["value"], confidence, valid_cats


# ============================================================
# B. Recherche hybride avec categorie boost
# ============================================================
def hybrid_search(query, query_vec, filter_cats=None):
    """
    Recherche hybride Typesense :
      - BM25 sur nom_produit (x5), categorie (x10), text (x1)
      - Vectoriel sur embedding
      - Fusion RRF naturelle par Typesense
      - filter_cats (list[str]) : si fourni, filtre dur sur ces categories
    Retourne 50 candidats (groupes par id_produit).
    """
    vec_str = json.dumps(query_vec)
    params = {
        "q": query,
        "query_by": "nom_produit,categorie,text",
        "query_by_weights": "5,10,1",
        "vector_query": f"embedding:({vec_str}, k:{CANDIDATES})",
        "per_page": CANDIDATES,
        "group_by": "id_produit",
        "group_limit": 1,
        "typo_tokens_threshold": 3,
        "drop_tokens_threshold": 2,
    }
    if filter_cats:
        # Typesense filter_by syntaxe: categorie:=[`cat1`,`cat2`,...]
        escaped = ",".join(f"`{c}`" for c in filter_cats)
        params["filter_by"] = f"categorie:=[{escaped}]"
    t = time.time()
    res = ts_multi(params)
    lat = (time.time() - t) * 1000
    return res, lat


# ============================================================
# C. Re-rank Python pondere
# ============================================================
def rerank(groups, query, top_k=TOP_K):
    """
    Applique la formule :
      final = 0.50*vec + 0.20*bm25 + 0.20*name_match + 0.10*cat_match
    Tous scores normalises dans [0,1].
    """
    q_tokens = tokenize(query)
    if not q_tokens:
        return [], 0

    t = time.time()
    raw = []
    for g in groups:
        hits_list = g.get("hits", [])
        if not hits_list:
            continue
        hit = hits_list[0]
        doc = hit["document"]

        # vector distance : deja retourne par Typesense (0 = identique, 2 = oppose en cosine)
        vec_dist = hit.get("vector_distance")
        vec_raw = 1 - min(vec_dist or 1.0, 1.0)  # similarite dans [0,1]

        # text match score (BM25-ish)
        tm = hit.get("text_match", 0) or 0

        # matching tokens sur nom_produit
        name_tokens = tokenize(doc.get("nom_produit", ""))
        name_match = len(q_tokens & name_tokens) / len(q_tokens)

        # matching tokens sur categorie
        cat_tokens = tokenize(doc.get("categorie", ""))
        cat_match = len(q_tokens & cat_tokens) / len(q_tokens)

        raw.append({
            "doc": doc,
            "vec_score": vec_raw,
            "text_raw": tm,
            "name_match": name_match,
            "cat_match": cat_match,
        })

    # Normalisation BM25 par batch (divise par le max)
    max_text = max((r["text_raw"] for r in raw), default=0) or 1

    for r in raw:
        r["text_score"] = r["text_raw"] / max_text if max_text > 0 else 0
        r["final_score"] = (
            W_VECTOR * r["vec_score"]
            + W_BM25 * r["text_score"]
            + W_NAME * r["name_match"]
            + W_CAT * r["cat_match"]
        )
        # Penalisation du bruit BM25 pur :
        # si le vecteur est faible ET le nom matche peu, c'est probablement
        # un match fortuit sur un mot dans la description
        if PENALTY_NOISE_BM25 and r["vec_score"] < 0.20 and r["name_match"] < 0.50:
            r["final_score"] *= 0.3
            r["penalty"] = "noise_bm25"
        else:
            r["penalty"] = ""

    raw.sort(key=lambda x: -x["final_score"])
    lat = (time.time() - t) * 1000
    return raw[:top_k], lat


# ============================================================
# D. Affichage
# ============================================================
def display(ranked, ts_lat, rr_lat, cat_detected, cat_conf, filter_cats, query):
    print(f"\n{'='*116}")
    print(f"  REQUETE : \"{query}\"  ({len(query.split())} mots)")
    print(f"  Categorie detectee : {cat_detected!r}  (confiance={cat_conf:.0%})")
    if filter_cats:
        print(f"  FILTER_BY applique : {filter_cats}")
    print(f"  Latences : Typesense={ts_lat:.0f}ms | re-rank={rr_lat:.0f}ms | TOTAL={ts_lat+rr_lat:.0f}ms")
    print(f"{'='*116}")
    print(f"  {'#':>2}  {'score':>6}  [vec  bm25 nom  cat]  {'pen':<10}  {'nom_produit':<50}  {'categorie':<28}")
    print(f"  {'-'*114}")
    for i, r in enumerate(ranked, 1):
        d = r["doc"]
        nom = (d.get("nom_produit") or "")[:48]
        cat = (d.get("categorie") or "?")[:26]
        nm = r['name_match'] * 100
        cm = r['cat_match'] * 100
        pen = r.get('penalty', '')
        print(f"  {i:>2}  {r['final_score']:>6.3f}  "
              f"[{r['vec_score']:.2f} {r['text_score']:.2f} {nm:3.0f}% {cm:3.0f}%]  "
              f"{pen:<10}  {nom:<50}  {cat}")


# ============================================================
# PIPELINE COMPLET
# ============================================================
def run_query(query, query_vecs):
    vec = query_vecs.get(query)
    if not vec:
        print(f"[ERREUR] Pas de vecteur pre-calcule pour '{query}'")
        print(f"         Dispos: {sorted(query_vecs.keys())}")
        return

    # 1. Detect categories
    t = time.time()
    cat_detected, cat_conf, top_cats = detect_categories(query)
    detect_lat = (time.time() - t) * 1000

    # 2. Filter_by si confiance suffisante
    filter_cats = top_cats if cat_conf >= CAT_FILTER_THRESHOLD else None

    # 3. Hybrid search
    res, ts_lat = hybrid_search(query, vec, filter_cats=filter_cats)
    groups = res.get("grouped_hits", [])

    # Fallback : si filter_by a trop reduit les resultats, refaire sans
    if filter_cats and len(groups) < 5:
        print(f"  [INFO] filter_by trop restrictif ({len(groups)} res), fallback sans filtre")
        res, ts_lat = hybrid_search(query, vec, filter_cats=None)
        groups = res.get("grouped_hits", [])
        filter_cats = None

    # 4. Rerank
    ranked, rr_lat = rerank(groups, query)

    # 5. Display
    print(f"\n  [detect_category: {detect_lat:.0f}ms]", end=" ")
    display(ranked, ts_lat, rr_lat, cat_detected, cat_conf, filter_cats, query)

    total = detect_lat + ts_lat + rr_lat
    return total


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

    latencies = []
    for q in queries:
        lat = run_query(q, query_vecs)
        if lat:
            latencies.append(lat)

    if latencies:
        print(f"\n\n{'='*60}")
        print(f"  RESUME LATENCES (total per query)")
        print(f"{'='*60}")
        print(f"  min  = {min(latencies):.0f} ms")
        print(f"  max  = {max(latencies):.0f} ms")
        print(f"  moy  = {sum(latencies)/len(latencies):.0f} ms")


if __name__ == "__main__":
    main()
