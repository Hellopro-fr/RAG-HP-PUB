"""
Re-rank Python pondere sur les top-N candidats retournes par Typesense.

Formule (hybrid, use_vector=True) :
    final = 0.55 * vec_score
          + 0.10 * bm25_score (normalise par batch)
          + 0.25 * name_match (tokens query inclus dans nom_produit)
          + 0.10 * cat_match  (tokens query inclus dans categorie)
Penalite si vec < 0.20 AND name_match < 0.50 -> x 0.3

Formule (BM25 only, use_vector=False) :
    final = 0.00 * vec_score  (pas de signal vecteur disponible)
          + 0.20 * bm25_score
          + 0.60 * name_match
          + 0.20 * cat_match
Penalite si name_match < 0.20 AND cat_match < 0.50 -> x 0.3
(sans vecteur, on s'appuie davantage sur le nom qui est le signal le plus
 robuste pour les queries de type "categorie + adjectif").

A4 (2026-05-18) -- Ponderation IDF des tokens
---------------------------------------------
name_match et cat_match sont ponderes par l'IDF des tokens query (inverse
document frequency calculee offline sur l'ensemble des nom_produit).

Exemple "melangeur conique" :
  - "conique" rare dans le catalogue -> idf eleve (~3.0)
  - "melangeur" plus commun           -> idf moyen (~1.5)
  Produit "Saleuse a cuve conique" (matche conique, pas melangeur) :
    name_match_simple = 1/2 = 0.50
    name_match_idf    = 3.0 / (3.0 + 1.5) = 0.67
  Produit "Mixeur peinture" (matche aucun token, mais titre semantique proche) :
    name_match_simple = 0/2 = 0.00
    name_match_idf    = 0.00 (inchange)

Effet : les produits qui contiennent les tokens rares de la query remontent
au-dessus de ceux qui ne contiennent que les tokens communs.

Si le fichier IDF n'est pas charge (idf_available()=False, ex. fresh deploy
sans avoir lance compute_idf.py), on bascule automatiquement sur le ratio
simple : aucune regression possible vs le comportement actuel.
"""
from typing import Dict, List, Any, Set

from app.core.credentials import settings
from app.services.idf_loader import get_idf, idf_available
from app.utils.text import tokenize


# Poids alternatifs quand on n'a pas de signal vecteur (BM25 pur)
_W_VECTOR_NOVEC = 0.00
_W_BM25_NOVEC   = 0.20
_W_NAME_NOVEC   = 0.60
_W_CAT_NOVEC    = 0.20


def _idf_weighted_match(q_tokens: Set[str], doc_tokens: Set[str]) -> float:
    """
    Ratio de match pondere par IDF entre q_tokens et doc_tokens.
    Si l'IDF n'est pas disponible -> fallback ratio simple
    (= comportement historique, aucune regression).

    Resultat entre 0.0 (aucun match) et 1.0 (tous les tokens query matches).
    """
    if not q_tokens:
        return 0.0

    if not idf_available():
        # Fallback : ratio simple historique
        return len(q_tokens & doc_tokens) / len(q_tokens)

    matched = q_tokens & doc_tokens
    if not matched:
        return 0.0

    sum_matched = sum(get_idf(t) for t in matched)
    sum_total = sum(get_idf(t) for t in q_tokens)
    if sum_total <= 0:
        # Garde-fou : tous les tokens query ont idf=0 (theoriquement impossible
        # avec idf lisse log((N+1)/(df+1))+1 >= 1) -> ratio simple
        return len(matched) / len(q_tokens)
    return sum_matched / sum_total


def rerank_candidates(
    groups: List[Dict[str, Any]],
    query: str,
    use_vector: bool = True,
) -> List[Dict[str, Any]]:
    """
    groups = Typesense `grouped_hits` (par id_produit).
    Retourne une liste d'objets scored tries par final_score desc.

    Si `use_vector=False`, applique une formule rebalancee (name_match domine)
    et une penalite adaptee (sans signal vectoriel, le bruit BM25 se detecte
    via name_match + cat_match).
    """
    q_tokens = tokenize(query)
    if not q_tokens or not groups:
        return []

    # Choix des poids
    if use_vector:
        w_vec  = settings.RERANK_W_VECTOR
        w_bm25 = settings.RERANK_W_BM25
        w_name = settings.RERANK_W_NAME
        w_cat  = settings.RERANK_W_CAT
    else:
        w_vec  = _W_VECTOR_NOVEC
        w_bm25 = _W_BM25_NOVEC
        w_name = _W_NAME_NOVEC
        w_cat  = _W_CAT_NOVEC

    raw = []
    for g in groups:
        hits = g.get("hits", [])
        if not hits:
            continue
        hit = hits[0]
        doc = hit["document"]

        vec_dist = hit.get("vector_distance")
        # Quand use_vector=False : vector_distance est absent -> score 0.
        vec_score = 1 - min(vec_dist or 1.0, 1.0) if use_vector else 0.0
        tm_raw = hit.get("text_match", 0) or 0

        # A4 : name_match et cat_match desormais ponderes par IDF (si dispo).
        name_tokens = tokenize(doc.get("nom_produit", ""))
        name_match = _idf_weighted_match(q_tokens, name_tokens)

        cat_tokens = tokenize(doc.get("categorie", ""))
        cat_match = _idf_weighted_match(q_tokens, cat_tokens)

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
            w_vec  * r["vec_score"]
            + w_bm25 * r["bm25_score"]
            + w_name * r["name_match"]
            + w_cat  * r["cat_match"]
        )
        # Penalite bruit (adaptee selon presence du signal vecteur)
        if use_vector:
            noise = r["vec_score"] < 0.20 and r["name_match"] < 0.50
        else:
            # Sans vecteur : on flag un bruit si aucun signal textuel fort
            noise = r["name_match"] < 0.20 and r["cat_match"] < 0.50
        if noise:
            r["final_score"] *= 0.3
            r["penalty"] = "noise_bm25" if use_vector else "noise_text"
        else:
            r["penalty"] = ""

    raw.sort(key=lambda x: -x["final_score"])
    return raw
