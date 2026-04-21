"""
Service de recherche hybride Typesense :
  1. Detection categorie via facet + prefix-match filter
  2. Hybrid search (BM25 sur nom_produit/categorie/text + kNN sur embedding)
  3. Re-rank Python pondere sur top-N
"""
import json
import logging
import time
from typing import Dict, List, Optional, Any

from app.core.credentials import settings
from app.core.typesense_client import typesense_client
from app.services.category_detector import detect_categories
from app.services.reranker import rerank_candidates

logger = logging.getLogger(__name__)


def search(
    query: str,
    query_vector: List[float],
    collection: Optional[str] = None,
    top_k: Optional[int] = None,
    candidates: Optional[int] = None,
    apply_filter_by_category: bool = True,
) -> Dict[str, Any]:
    """
    Execute une recherche hybride avec fallback sans filter_by si trop restrictif.
    Retourne un dict {query, results, detected_cat, confidence, filter_cats,
    latency_ms_ts, latency_ms_rerank}.
    """
    collection = collection or settings.TYPESENSE_COLLECTION
    top_k = top_k or settings.DEFAULT_TOP_K
    candidates = candidates or settings.CANDIDATES_TOP_K

    # 1. Category detection
    t0 = time.time()
    cat_detected, conf, valid_cats = detect_categories(query, collection=collection)
    detect_ms = (time.time() - t0) * 1000

    # 2. filter_by decision
    filter_cats = None
    if apply_filter_by_category and conf >= settings.CAT_FILTER_THRESHOLD and valid_cats:
        filter_cats = valid_cats

    # 3. Hybrid search
    t1 = time.time()
    ts_result = _hybrid_typesense_search(
        query, query_vector, collection, candidates, filter_cats=filter_cats,
    )
    groups = ts_result.get("grouped_hits", [])

    # Fallback : si filter_by trop restrictif (< 5 resultats), retry sans filtre
    if filter_cats and len(groups) < 5:
        logger.info(
            "filter_by trop restrictif (%d res) pour query=%r, fallback sans filtre",
            len(groups), query,
        )
        ts_result = _hybrid_typesense_search(
            query, query_vector, collection, candidates, filter_cats=None,
        )
        groups = ts_result.get("grouped_hits", [])
        filter_cats = None
    ts_ms = (time.time() - t1) * 1000

    # 4. Re-rank
    t2 = time.time()
    ranked = rerank_candidates(groups, query)
    rerank_ms = (time.time() - t2) * 1000

    # 5. Shape output
    hits_out = []
    for r in ranked[:top_k]:
        d = r["doc"]
        hits_out.append({
            "id_produit":   d.get("id_produit"),
            "nom_produit":  d.get("nom_produit") or "",
            "categorie":    d.get("categorie") or "",
            "fournisseur":  d.get("fournisseur") or "",
            "marque":       d.get("marque") or "",
            "prix_ht":      d.get("prix_ht"),
            "score":        round(r["final_score"], 4),
            "scores_detail": {
                "vector":     round(r["vec_score"], 4),
                "bm25":       round(r["bm25_score"], 4),
                "name_match": round(r["name_match"], 4),
                "cat_match":  round(r["cat_match"], 4),
                "penalty":    r["penalty"],
            },
        })

    return {
        "query": query,
        "detected_category": cat_detected,
        "detection_confidence": round(conf, 3),
        "filter_by_category": filter_cats,
        "latency_ms": {
            "detect":  round(detect_ms),
            "typesense": round(ts_ms),
            "rerank":  round(rerank_ms),
            "total":   round(detect_ms + ts_ms + rerank_ms),
        },
        "total_candidates": len(groups),
        "results": hits_out,
    }


def _hybrid_typesense_search(
    query: str,
    query_vector: List[float],
    collection: str,
    candidates: int,
    filter_cats: Optional[List[str]] = None,
) -> Dict[str, Any]:
    vec_str = json.dumps(query_vector)
    params = {
        "collection": collection,
        "q": query,
        "query_by": "nom_produit,categorie,text",
        "query_by_weights": "5,10,1",
        "vector_query": f"embedding:({vec_str}, k:{candidates})",
        "per_page": candidates,
        "group_by": "id_produit",
        "group_limit": 1,
        "typo_tokens_threshold": 3,
        "drop_tokens_threshold": 2,
    }
    if filter_cats:
        escaped = ",".join(f"`{c}`" for c in filter_cats)
        params["filter_by"] = f"categorie:=[{escaped}]"

    res = typesense_client.multi_search({"searches": [params]})
    return res["results"][0]
