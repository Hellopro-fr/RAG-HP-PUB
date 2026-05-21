"""
brands_loader.py
================
Charge la liste des marques (mono-token) depuis Typesense au runtime.
Permet au reranker de detecter quand une query contient une marque
("urinoir delabie") et d'exiger que le TYPE produit soit egalement
satisfait (sinon le produit Delabie qui n'est pas un urinoir remonte
en pos 1).

Source : facets Typesense sur `marque` + `fournisseur` (les 2 sources
de "marques" dans le schema actuel). Mono-token uniquement pour l'instant
(detection rapide en O(1) sur les tokens query).

Comportement si Typesense indisponible : `get_brands_set()` retourne set()
-> R2 brand_filter inactif -> reranker comporte comme avant (aucune
regression).
"""
import logging
from typing import Optional, Set

from app.core.credentials import settings
from app.core.typesense_client import typesense_client
from app.utils.text import tokenize

logger = logging.getLogger(__name__)


# Etat global (singleton, charge a la 1ere demande)
_brands_set: Optional[Set[str]] = None
_load_attempted: bool = False


def _load_brands() -> Set[str]:
    """
    Charge la liste des marques mono-token depuis Typesense via facets.
    Cache singleton. Fallback safe en cas d'erreur.
    """
    global _brands_set, _load_attempted

    if _brands_set is not None:
        return _brands_set
    if _load_attempted:
        return _brands_set or set()
    _load_attempted = True

    try:
        # Charge facets marque + fournisseur via multi_search
        params = {
            "collection": settings.TYPESENSE_COLLECTION,
            "q": "*",
            "query_by": "nom_produit",
            "per_page": 1,
            "facet_by": "marque,fournisseur",
            "max_facet_values": 10000,
        }
        res = typesense_client.multi_search({"searches": [params]})
        result = res.get("results", [{}])[0] if res.get("results") else {}
        facets = result.get("facet_counts", [])

        brands: Set[str] = set()
        n_multi_token_skipped = 0

        for facet in facets:
            for c in facet.get("counts", []):
                value = (c.get("value") or "").strip()
                if not value:
                    continue
                # Tokenise la marque (filtre min 2 chars, normalise accents/casse)
                tokens = tokenize(value)
                # Pour l'instant on garde uniquement les marques MONO-TOKEN
                # (ex: "delabie", "xcmg", "zoomlion"). Les marques multi-mots
                # comme "Saint Gobain" sont skip car la detection serait plus
                # complexe (matching de sequence). A enrichir plus tard si
                # besoin business.
                if len(tokens) == 1:
                    brands |= tokens
                else:
                    n_multi_token_skipped += 1

        _brands_set = brands
        logger.info(
            "Brands loaded from Typesense facets: %d single-token brands (skipped %d multi-token brands)",
            len(brands), n_multi_token_skipped,
        )
    except Exception as e:
        logger.warning(
            "Failed to load brands from Typesense (%s) - reranker will skip brand detection (R2 inactive)",
            e,
        )
        _brands_set = set()

    return _brands_set


def get_brands_set() -> Set[str]:
    """Retourne le set des marques mono-token connues."""
    return _load_brands()


def is_brand(token: str) -> bool:
    """True si le token est une marque connue (mono-token, normalise)."""
    return token in _load_brands()


def split_query_brand_type(q_tokens: Set[str]) -> "tuple[Set[str], Set[str]]":
    """
    Separe les tokens query en (brand_tokens, type_tokens).

    Ex : query "urinoir delabie" + brands set incluant "delabie" ->
         brand_tokens = {"delabie"}, type_tokens = {"urinoir"}

    Si la query ne contient aucune marque connue : brand_tokens vide,
    type_tokens = q_tokens (R2 inactif sur cette query).
    """
    brands = _load_brands()
    if not brands:
        return set(), set(q_tokens)
    brand_tokens = q_tokens & brands
    type_tokens = q_tokens - brand_tokens
    return brand_tokens, type_tokens


def brands_available() -> bool:
    """True si la liste des marques est chargee."""
    return bool(_load_brands())


def reset_cache_for_test():
    """Helper tests : force le rechargement au prochain appel."""
    global _brands_set, _load_attempted
    _brands_set = None
    _load_attempted = False
