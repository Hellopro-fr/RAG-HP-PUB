"""
Re-rank Python pondere sur les top-N candidats retournes par Typesense.

Formule (hybrid, use_vector=True) :
    final = 0.55 * vec_score
          + 0.10 * bm25_score (normalise par batch)
          + 0.25 * name_match (tokens query inclus dans nom_produit)
          + 0.10 * cat_match  (tokens query inclus dans categorie)
Penalite si vec < 0.20 AND name_match < 0.50 -> x 0.3

Formule (BM25 only, use_vector=False) :
    final = 0.00 * vec_score
          + 0.20 * bm25_score
          + 0.60 * name_match
          + 0.20 * cat_match
Penalite si name_match < 0.20 AND cat_match < 0.50 -> x 0.3

A4 (2026-05-18) -- Ponderation IDF des tokens
---------------------------------------------
name_match et cat_match sont ponderes par l'IDF des tokens query. Le token
rare ("conique") pese plus que le token commun ("melangeur").

A6 (2026-05-20) -- Support synonymes dans le matching
------------------------------------------------------
Un token query est considere "couvert" si lui-meme OU un de ses synonymes
Typesense apparait dans le doc. Resout "crane" -> "Grue XCMG" (multilingue).

A7 (2026-05-21) -- R3 : Coverage strict sur tokens query
---------------------------------------------------------
Si la majorite des tokens query ne sont PAS couverts (ni en direct, ni via
synonyme, ni dans nom_produit, ni dans categorie), on applique une penalite
progressive sur final_score. Resout `barre laser a led` -> scanner code-barre
(la query a 3 tokens, le scanner n'en matche que 2/3 -> penalite).

Seuils :
  coverage < 50% : score * 0.5  (50% penalty)
  coverage < 70% : score * 0.75 (25% penalty)
  coverage >= 70%: pas de penalite

A8 (2026-05-21) -- R2 : Marque comme contrainte forte
------------------------------------------------------
Quand une query contient une marque connue + au moins un autre token (type
produit), on exige que le TYPE soit egalement couvert. Sinon penalite forte.
Resout `urinoir delabie` -> Distributeur Delabie en pos 1 (le distributeur
matche "delabie" mais pas "urinoir" -> penalite).

Si pas de marque dans la query OU pas de type token (juste une marque) :
R2 inactif sur cette query, comportement A7 standard.
"""
from typing import Dict, List, Any, Set, Optional

from app.core.credentials import settings
from app.services.brands_loader import split_query_brand_type, brands_available
from app.services.idf_loader import get_idf, idf_available
from app.services.synonyms_loader import get_synonyms_map
from app.utils.text import tokenize


# Poids alternatifs quand on n'a pas de signal vecteur (BM25 pur)
_W_VECTOR_NOVEC = 0.00
_W_BM25_NOVEC   = 0.20
_W_NAME_NOVEC   = 0.60
_W_CAT_NOVEC    = 0.20

# A7 R3 : seuils de pénalité coverage strict
_R3_COVERAGE_STRONG_PENALTY  = 0.50  # < 50% des tokens couverts -> score * 0.5
_R3_COVERAGE_WEAK_PENALTY    = 0.70  # < 70% -> score * 0.75
_R3_STRONG_FACTOR = 0.5
_R3_WEAK_FACTOR   = 0.75

# A8 R2 : penalite si marque presente dans query mais type produit absent du doc
_R2_MISSING_TYPE_FACTOR = 0.3


def _is_covered(
    token: str,
    name_tokens: Set[str],
    cat_tokens: Set[str],
    syn_map: Optional[Dict[str, Set[str]]],
) -> bool:
    """
    True si `token` est couvert par le doc :
    - directement dans nom_produit ou categorie, OU
    - via un synonyme present dans nom_produit ou categorie.
    """
    if token in name_tokens or token in cat_tokens:
        return True
    if syn_map:
        equivs = syn_map.get(token)
        if equivs and (not equivs.isdisjoint(name_tokens) or not equivs.isdisjoint(cat_tokens)):
            return True
    return False


def _idf_weighted_match(
    q_tokens: Set[str],
    doc_tokens: Set[str],
    syn_map: Optional[Dict[str, Set[str]]] = None,
) -> float:
    """
    Ratio de match pondere par IDF avec support synonymes.

    Un token query est "couvert" s'il-meme ou un de ses synonymes est dans
    doc_tokens. Score = sum(idf(t)) pour t couvert / sum(idf(t)) pour t in q_tokens.

    Resultat entre 0.0 et 1.0. Fallback ratio simple si IDF indispo.
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

        if t in doc_tokens:
            sum_matched += weight
            n_matched += 1
            continue

        if syn_map is not None:
            equivs = syn_map.get(t)
            if equivs and not equivs.isdisjoint(doc_tokens):
                sum_matched += weight
                n_matched += 1

    if sum_total <= 0:
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
    """
    q_tokens = tokenize(query)
    if not q_tokens or not groups:
        return []

    # A6 : mapping synonymes (lazy + cache)
    syn_map = get_synonyms_map() or None

    # A8 R2 : detection marque dans la query (et separation brand/type tokens)
    brand_tokens, type_tokens = split_query_brand_type(q_tokens) if brands_available() else (set(), set(q_tokens))
    # R2 actif uniquement si la query contient une marque ET au moins un autre token (type)
    r2_active = bool(brand_tokens) and bool(type_tokens)

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
        vec_score = 1 - min(vec_dist or 1.0, 1.0) if use_vector else 0.0
        tm_raw = hit.get("text_match", 0) or 0

        name_tokens = tokenize(doc.get("nom_produit", ""))
        cat_tokens = tokenize(doc.get("categorie", ""))

        # A4+A6 : matching IDF + synonymes
        name_match = _idf_weighted_match(q_tokens, name_tokens, syn_map=syn_map)
        cat_match = _idf_weighted_match(q_tokens, cat_tokens, syn_map=syn_map)

        # A7 R3 : ratio strict de tokens couverts (sans ponderation IDF)
        # Un token est couvert si dans name OU cat OU via synonyme.
        n_covered = sum(
            1 for t in q_tokens
            if _is_covered(t, name_tokens, cat_tokens, syn_map)
        )
        coverage_ratio = n_covered / len(q_tokens)

        # A8 R2 : verifier que les type_tokens sont couverts si une marque est presente
        # Si R2 actif et type_tokens NON couverts -> doc ne satisfait pas l'intention
        # "type X de la marque Y" -> penalite forte.
        r2_missing_type = False
        if r2_active:
            type_covered = any(
                _is_covered(t, name_tokens, cat_tokens, syn_map) for t in type_tokens
            )
            if not type_covered:
                r2_missing_type = True

        raw.append({
            "doc": doc,
            "vec_score": vec_score,
            "tm_raw": tm_raw,
            "name_match": name_match,
            "cat_match": cat_match,
            "coverage_ratio": coverage_ratio,
            "r2_missing_type": r2_missing_type,
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

        penalties = []

        # Penalite bruit historique (A1) — vec faible + name_match faible
        if use_vector:
            noise = r["vec_score"] < 0.20 and r["name_match"] < 0.50
        else:
            noise = r["name_match"] < 0.20 and r["cat_match"] < 0.50
        if noise:
            r["final_score"] *= 0.3
            penalties.append("noise_bm25" if use_vector else "noise_text")

        # A7 R3 : penalite coverage stricte
        if r["coverage_ratio"] < _R3_COVERAGE_STRONG_PENALTY:
            r["final_score"] *= _R3_STRONG_FACTOR
            penalties.append("low_coverage_50")
        elif r["coverage_ratio"] < _R3_COVERAGE_WEAK_PENALTY:
            r["final_score"] *= _R3_WEAK_FACTOR
            penalties.append("low_coverage_70")

        # A8 R2 : penalite si marque presente mais type produit absent
        if r["r2_missing_type"]:
            r["final_score"] *= _R2_MISSING_TYPE_FACTOR
            penalties.append("missing_type_with_brand")

        r["penalty"] = " ".join(penalties)

    raw.sort(key=lambda x: -x["final_score"])
    return raw
