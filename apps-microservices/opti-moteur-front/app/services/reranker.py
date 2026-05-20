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

A6 (2026-05-20) -- Support synonymes dans le matching
------------------------------------------------------
Un token query est considere "couvert" par le doc si lui-meme OU un de ses
synonymes Typesense apparait dans nom_produit / categorie. Resout les cas
multilingues comme "crane" -> "Grue XCMG" (le synonyme manual-grue contient
"crane" + "grue" + "grues" + ...).

Sans synonymes (Typesense indisponible ou pas configure) : fallback sur le
matching strict (= comportement A4). Aucune regression possible.
"""
from typing import Dict, List, Any, Set, Optional

from app.core.credentials import settings
from app.services.idf_loader import get_idf, idf_available
from app.services.synonyms_loader import get_synonyms_map
from app.utils.text import tokenize


# Poids alternatifs quand on n'a pas de signal vecteur (BM25 pur)
_W_VECTOR_NOVEC = 0.00
_W_BM25_NOVEC   = 0.20
_W_NAME_NOVEC   = 0.60
_W_CAT_NOVEC    = 0.20


def _idf_weighted_match(
    q_tokens: Set[str],
    doc_tokens: Set[str],
    syn_map: Optional[Dict[str, Set[str]]] = None,
) -> float:
    """
    Ratio de match pondere par IDF, avec support synonymes optionnel.

    Logique :
      - Pour chaque token query, on verifie s'il est "couvert" par le doc.
        Un token est couvert si lui-meme OU un de ses synonymes est dans doc_tokens.
      - Score = somme des IDF des tokens couverts / somme des IDF de TOUS les tokens query.

    Si IDF non disponible -> fallback ratio simple (= comportement historique).
    Si syn_map non fourni -> matching strict (comportement A4 sans A6).

    Resultat entre 0.0 (aucun token couvert) et 1.0 (tous couverts).
    """
    if not q_tokens:
        return 0.0

    use_idf = idf_available()
    sum_total = 0.0
    sum_matched = 0.0
    n_matched = 0

    for t in q_tokens:
        weight = get_idf(t) if use_idf else 1.0
        sum_total += weight

        # Direct match (token litteral dans le doc)
        if t in doc_tokens:
            sum_matched += weight
            n_matched += 1
            continue

        # Synonym match (un equivalent du token est dans le doc)
        if syn_map is not None:
            equivs = syn_map.get(t)
            if equivs and not equivs.isdisjoint(doc_tokens):
                sum_matched += weight
                n_matched += 1
                continue

    if sum_total <= 0:
        # Garde-fou (theoriquement impossible avec idf lisse >= 1)
        return n_matched / len(q_tokens)

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

    # A6 : charge le mapping synonymes (lazy + cache). {} si non disponible.
    syn_map = get_synonyms_map() or None

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

        # A4+A6 : name_match et cat_match ponderes par IDF + expansion synonymes.
        name_tokens = tokenize(doc.get("nom_produit", ""))
        name_match = _idf_weighted_match(q_tokens, name_tokens, syn_map=syn_map)

        cat_tokens = tokenize(doc.get("categorie", ""))
        cat_match = _idf_weighted_match(q_tokens, cat_tokens, syn_map=syn_map)

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
