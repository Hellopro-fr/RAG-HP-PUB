"""
Re-rank Python pondere sur les top-N candidats retournes par Typesense.
Formule :
    final = W_VECTOR * vec_score
          + W_BM25   * bm25_score (normalise par batch)
          + W_NAME   * name_match (tokens query inclus dans nom_produit)
          + W_CAT    * cat_match  (tokens query inclus dans categorie)

Penalite si vec < 0.20 AND name_match < 0.50 -> multiplication par 0.3
(elimine les matches BM25 fortuits sans signal semantique ni nom).
"""
from typing import Dict, List, Any

from app.core.credentials import settings
from app.utils.text import tokenize


def rerank_candidates(groups: List[Dict[str, Any]], query: str) -> List[Dict[str, Any]]:
    """
    groups = Typesense `grouped_hits` (par id_produit).
    Retourne une liste d'objets scored tries par final_score desc.
    """
    q_tokens = tokenize(query)
    if not q_tokens or not groups:
        return []

    raw = []
    for g in groups:
        hits = g.get("hits", [])
        if not hits:
            continue
        hit = hits[0]
        doc = hit["document"]

        vec_dist = hit.get("vector_distance")
        vec_score = 1 - min(vec_dist or 1.0, 1.0)
        tm_raw = hit.get("text_match", 0) or 0

        name_tokens = tokenize(doc.get("nom_produit", ""))
        name_match = len(q_tokens & name_tokens) / max(len(q_tokens), 1)

        cat_tokens = tokenize(doc.get("categorie", ""))
        cat_match = len(q_tokens & cat_tokens) / max(len(q_tokens), 1)

        raw.append({
            "doc": doc,
            "vec_score": vec_score,
            "tm_raw": tm_raw,
            "name_match": name_match,
            "cat_match": cat_match,
        })

    # Normalisation BM25 par batch
    max_tm = max((r["tm_raw"] for r in raw), default=0) or 1

    for r in raw:
        r["bm25_score"] = r["tm_raw"] / max_tm if max_tm > 0 else 0.0
        r["final_score"] = (
            settings.RERANK_W_VECTOR * r["vec_score"]
            + settings.RERANK_W_BM25  * r["bm25_score"]
            + settings.RERANK_W_NAME  * r["name_match"]
            + settings.RERANK_W_CAT   * r["cat_match"]
        )
        # Penalite bruit BM25 pur
        if r["vec_score"] < 0.20 and r["name_match"] < 0.50:
            r["final_score"] *= 0.3
            r["penalty"] = "noise_bm25"
        else:
            r["penalty"] = ""

    raw.sort(key=lambda x: -x["final_score"])
    return raw
