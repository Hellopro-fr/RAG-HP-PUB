"""
POC Typesense - Benchmark recherche CamemBERT 1024
Compare 3 modes sur la requete "armoire medicale" (cas Elena):
  1. Semantique pur  (simule Milvus actuel)
  2. BM25 pur        (keyword only)
  3. Hybrid Typesense avec alpha dynamique (la solution proposee)
"""

import json
import os
import sys
import time
import requests
import typesense

# ============================================================
# CONFIG
# ============================================================
TYPESENSE_HOST = "localhost"
TYPESENSE_PORT = "8108"
TYPESENSE_API_KEY = "hp_poc_2026"
COLLECTION_NAME = "produits_hellopro_cam"
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

client = typesense.Client({
    "api_key": TYPESENSE_API_KEY,
    "nodes": [{"host": TYPESENSE_HOST, "port": TYPESENSE_PORT, "protocol": "http"}],
    "connection_timeout_seconds": 10,
})

# Ground truth pour la requete "armoire medicale" (cas Elena)
RELEVANT_CATEGORIES = {"2007191", "2017274"}   # Armoire medicale + Armoires pharmacie
SEMI_CATEGORIES = {"1002240", "2005800", "2003362"}  # Securite, Refrigeree, Precision


def classify(cat_id):
    if cat_id in RELEVANT_CATEGORIES:
        return "[OK] PERTINENT"
    if cat_id in SEMI_CATEGORIES:
        return "[~~] SEMI   "
    return "[XX] BRUIT  "


def load_query_embeddings():
    """Map: texte_requete -> vecteur 1024."""
    fpath = os.path.join(DATA_DIR, "query_embeddings.json")
    with open(fpath, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {item["text"]: item["vector"] for item in data}


# ============================================================
# METHODES DE RECHERCHE
# ============================================================
def _multi_search(params):
    """Wrapper multi_search (POST) pour eviter la limite URL de 4000 chars."""
    body = {"searches": [{"collection": COLLECTION_NAME, **params}]}
    res = client.multi_search.perform(body, {})
    return res["results"][0]


def search_semantic(query, query_vec, top_k=10):
    """Vectoriel pur - simule Milvus actuel."""
    vec_str = json.dumps(query_vec)
    params = {
        "q": "*",
        "vector_query": f"embedding:({vec_str}, k:{top_k})",
        "per_page": top_k,
    }
    t = time.time()
    res = _multi_search(params)
    return res, (time.time() - t) * 1000


def search_bm25(query, top_k=10):
    """Keyword BM25 pur."""
    params = {
        "q": query,
        "query_by": "nom,rubrique,description",
        "query_by_weights": "5,3,1",
        "per_page": top_k,
        "typo_tokens_threshold": 3,
        "drop_tokens_threshold": 2,
    }
    t = time.time()
    res = _multi_search(params)
    return res, (time.time() - t) * 1000


def search_hybrid(query, query_vec, top_k=10, alpha=None):
    """
    Hybrid = BM25 + vectoriel fusionnes par Typesense (RRF auto).
    alpha dynamique selon longueur de query:
      1-2 mots -> alpha bas (privilegie keyword, bon pour requetes courtes type commercial)
      5+ mots  -> alpha haut (privilegie semantique)
    Typesense fait la fusion RRF automatiquement; alpha n'est pas un parametre
    direct, mais on peut ajuster query_by_weights pour donner plus de poids aux
    champs texte ou a l'embedding.
    """
    if alpha is None:
        n = len(query.split())
        if n <= 2:
            text_w = "7,4,1"   # fort boost nom/rubrique pour requetes courtes
        elif n <= 4:
            text_w = "5,3,1"
        else:
            text_w = "3,2,1"
    else:
        text_w = "5,3,1"

    vec_str = json.dumps(query_vec)
    params = {
        "q": query,
        "query_by": "nom,rubrique,description",
        "query_by_weights": text_w,
        "vector_query": f"embedding:({vec_str}, k:{top_k})",
        "per_page": top_k,
        "typo_tokens_threshold": 3,
        "drop_tokens_threshold": 2,
    }
    t = time.time()
    res = _multi_search(params)
    return res, (time.time() - t) * 1000, text_w


# ============================================================
# AFFICHAGE
# ============================================================
def display(res, latency_ms, label, note=""):
    hits = res.get("hits", [])
    print(f"\n{'-'*78}")
    print(f"  {label}  {note}")
    print(f"  {len(hits)} resultats - {latency_ms:.0f}ms")
    print(f"{'-'*78}")

    for i, hit in enumerate(hits[:10], 1):
        d = hit["document"]
        tag = classify(d.get("categorie_id", "?"))
        nom = (d["nom"][:52] + "..") if len(d["nom"]) > 54 else d["nom"]
        print(f"  #{i:2d} {tag}  {nom:<55}  | {d['rubrique'][:25]}")

    # Precision metrics
    n = min(len(hits), 10)
    if n:
        p5 = sum(1 for h in hits[:5] if h["document"].get("categorie_id") in RELEVANT_CATEGORIES) / min(5, n)
        p10 = sum(1 for h in hits[:10] if h["document"].get("categorie_id") in RELEVANT_CATEGORIES) / n
        noise = sum(1 for h in hits[:10]
                    if h["document"].get("categorie_id") not in RELEVANT_CATEGORIES
                    and h["document"].get("categorie_id") not in SEMI_CATEGORIES)
        print(f"\n  P@5 = {p5:.0%}   P@10 = {p10:.0%}   Bruit top10 = {noise}   Latence = {latency_ms:.0f}ms")
        return {"p5": p5, "p10": p10, "noise": noise, "latency": latency_ms}
    return {"p5": 0, "p10": 0, "noise": 0, "latency": latency_ms}


# ============================================================
# MAIN
# ============================================================
def run_benchmark(query, query_vecs):
    vec = query_vecs.get(query)
    if not vec:
        print(f"[ERREUR] Pas de vecteur pre-calcule pour '{query}'")
        print(f"         Requetes disponibles: {list(query_vecs.keys())}")
        return

    print(f"\n{'='*78}")
    print(f"  REQUETE: \"{query}\"  ({len(query.split())} mots)")
    print(f"{'='*78}")

    # 1. Semantique pur (simule Milvus)
    r1, l1 = search_semantic(query, vec)
    m1 = display(r1, l1, "1. SEMANTIQUE PUR (simule Milvus actuel)")

    # 2. BM25 pur
    r2, l2 = search_bm25(query)
    m2 = display(r2, l2, "2. BM25 PUR (keyword seul)")

    # 3. Hybrid avec alpha dynamique
    r3, l3, tw = search_hybrid(query, vec)
    m3 = display(r3, l3, "3. HYBRID TYPESENSE", f"(query_by_weights={tw})")

    # Resume
    print(f"\n{'='*78}")
    print(f"  RESUME COMPARATIF - \"{query}\"")
    print(f"{'='*78}")
    print(f"  {'Methode':<32s} {'P@5':>6} {'P@10':>7} {'Bruit':>7} {'Latence':>10}")
    print(f"  {'-'*64}")
    for name, m in [("Semantique (simule Milvus)", m1), ("BM25 pur", m2), ("Hybrid Typesense", m3)]:
        print(f"  {name:<32s} {m['p5']:>5.0%} {m['p10']:>6.0%} {m['noise']:>6d}  {m['latency']:>7.0f}ms")


def main():
    try:
        requests.get(f"http://{TYPESENSE_HOST}:{TYPESENSE_PORT}/health", timeout=3).raise_for_status()
    except Exception as e:
        print(f"[ERREUR] Typesense injoignable: {e}")
        sys.exit(1)

    query_vecs = load_query_embeddings()
    print(f"[OK] {len(query_vecs)} requetes pre-embeddees chargees")
    print(f"     Disponibles: {', '.join(repr(q) for q in query_vecs.keys())}")

    # Cas principal: reproduire le scenario d'Elena
    run_benchmark("armoire medicale", query_vecs)

    # Cas additionnels
    print("\n\n")
    run_benchmark("armoire m\u00e9dicale", query_vecs)

    print("\n\nAutres requetes disponibles (modifier main() pour tester):")
    for q in query_vecs:
        print(f"  - \"{q}\"")


if __name__ == "__main__":
    main()
