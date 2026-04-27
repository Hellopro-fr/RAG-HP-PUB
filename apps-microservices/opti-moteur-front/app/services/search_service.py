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
    query_vector: Optional[List[float]] = None,
    collection: Optional[str] = None,
    top_k: Optional[int] = None,
    candidates: Optional[int] = None,
    offset: int = 0,
    apply_filter_by_category: bool = True,
) -> Dict[str, Any]:
    """
    Execute une recherche hybride (BM25 + kNN vecteur) OU BM25 pur selon la
    presence de query_vector. Fallback sans filter_by si trop restrictif.

    Si `query_vector` est None -> pipeline BM25 pur (pas d'appel vectoriel a
    Typesense, reranker sans poids vecteur). Utile pour benchmark sans embedding.
    """
    collection = collection or settings.TYPESENSE_COLLECTION
    top_k = top_k or settings.DEFAULT_TOP_K
    candidates = candidates or settings.CANDIDATES_TOP_K
    use_vector = query_vector is not None

    # 1. Category detection (inchange, text-only)
    t0 = time.time()
    cat_detected, conf, valid_cats = detect_categories(query, collection=collection)
    detect_ms = (time.time() - t0) * 1000

    # 2. filter_by decision
    filter_cats = None
    if apply_filter_by_category and conf >= settings.CAT_FILTER_THRESHOLD and valid_cats:
        filter_cats = valid_cats

    # 3. Hybrid or BM25-only search
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

    # 4. Re-rank (formule adaptee selon use_vector)
    t2 = time.time()
    ranked = rerank_candidates(groups, query, use_vector=use_vector)
    rerank_ms = (time.time() - t2) * 1000

    # 5. Shape output (applique offset pour pagination AJAX)
    hits_out = []
    paged = ranked[offset:offset + top_k] if offset > 0 else ranked[:top_k]
    for r in paged:
        d = r["doc"]
        hits_out.append({
            "id_produit":    d.get("id_produit"),
            "nom_produit":   d.get("nom_produit") or "",
            "categorie":     d.get("categorie") or "",
            # id_categorie : indispensable pour reconstruire l'URL fiche produit cote front
            # (pattern /<slug>-<id_categorie>-<id_produit>-produit.html). Sans ce champ,
            # PHP filtre et rejette les hits -> 0 resultat affiche malgre 30 hits API.
            "id_categorie":  str(d.get("id_categorie") or ""),
            "fournisseur":   d.get("fournisseur") or "",
            "id_fournisseur": str(d.get("id_fournisseur") or ""),
            "marque":        d.get("marque") or "",
            # etat / affichage : utilises cote PHP pour le boost "societe cliente"
            # (etat == 'Client' OU (etat == 'Pause' AND affichage == 'Complet')).
            "etat":          d.get("etat") or "",
            "affichage":     d.get("affichage") or "",
            "prix_ht":       d.get("prix_ht"),
            "score":         round(r["final_score"], 4),
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


# Limite Typesense : per_page + k pour hybrid search capped a 250.
# Au-dela on doit paginer via le parametre `page`.
_PER_PAGE_CAP = 250
# Nombre max de pages parallelisees via multi_search (= 4 x 250 = 1000 docs).
# Couvre les plus grosses categories HelloPro sans exploser la latence
# (multi_search fait les pages en parallele server-side).
_MAX_PAGES = 4


def _hybrid_typesense_search(
    query: str,
    query_vector: Optional[List[float]],
    collection: str,
    candidates: int,
    filter_cats: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Recherche paginee pour couvrir jusqu'a `candidates` documents uniques.

    Si `query_vector` est None -> BM25 pur (pas de vector_query envoye).
    Sinon -> hybrid BM25 + kNN sur embedding.

    Typesense capse `per_page` et `k` (vector kNN) a 250 pour les recherches
    hybrides. Pour remonter plus de candidats (utile pour les grosses
    categories >250 produits, ex. Perceuses a colonne = 587), on envoie
    plusieurs pages via multi_search (parallelisees server-side).

    Le dedup par id_produit est fait server-side via `group_by` au sein d'une
    page, puis client-side a travers les pages (un meme id_produit peut
    apparaitre sur plusieurs pages si ses chunks sont distribues).
    """
    per_page = min(max(candidates, 1), _PER_PAGE_CAP)
    num_pages = min((candidates + per_page - 1) // per_page, _MAX_PAGES)
    num_pages = max(num_pages, 1)

    base_params = {
        "collection": collection,
        "q": query,
        "query_by": "nom_produit,categorie,text",
        "query_by_weights": "5,10,1",
        "per_page": per_page,
        "group_by": "id_produit",
        "group_limit": 1,
        "typo_tokens_threshold": 3,
        "drop_tokens_threshold": 2,
    }
    # Ajoute le vector_query seulement si un vecteur est fourni (mode hybride)
    if query_vector is not None:
        vec_str = json.dumps(query_vector)
        base_params["vector_query"] = f"embedding:({vec_str}, k:{per_page})"
    if filter_cats:
        escaped = ",".join(f"`{c}`" for c in filter_cats)
        base_params["filter_by"] = f"categorie:=[{escaped}]"

    # Construit N pages, tous en une seule requete multi_search (parallele)
    searches = []
    for page in range(1, num_pages + 1):
        p = dict(base_params)
        p["page"] = page
        searches.append(p)

    res = typesense_client.multi_search({"searches": searches})
    page_results = res.get("results", [])

    # Merge cross-pages avec dedup par id_produit (garde le 1er hit rencontre
    # = meilleur rang Typesense, car les pages sont ordonnees par pertinence)
    seen_ids = set()
    merged_groups = []
    for page_result in page_results:
        for g in page_result.get("grouped_hits", []):
            hits = g.get("hits") or []
            if not hits:
                continue
            id_p = hits[0].get("document", {}).get("id_produit")
            if not id_p:
                continue
            if id_p in seen_ids:
                continue
            seen_ids.add(id_p)
            merged_groups.append(g)

    logger.debug(
        "_hybrid_typesense_search: %d pages, %d groupes uniques (candidates=%d, filter_cats=%s)",
        num_pages, len(merged_groups), candidates, filter_cats,
    )

    # On renvoie la meme structure que l'ancien retour pour ne rien casser en aval
    return {"grouped_hits": merged_groups}
