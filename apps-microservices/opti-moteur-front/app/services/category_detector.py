"""
Detection de la categorie dominante dans une requete via facet Typesense.
Applique ensuite un filtre de prefix-match pour ne garder que les categories
ou les query tokens apparaissent bien AU DEBUT du nom (evite les cascades).
"""
import logging
from typing import List, Optional, Tuple

from app.core.credentials import settings
from app.core.typesense_client import typesense_client
from app.utils.text import tokenize, is_prefix_match

logger = logging.getLogger(__name__)


def detect_categories(
    query: str,
    collection: Optional[str] = None,
    top_n: Optional[int] = None,
) -> Tuple[Optional[str], float, List[str]]:
    """
    Retourne (top_category, confidence, valid_categories_prefix_match).

    confidence = nb de matches sur top_cat / total matches (facet)
    valid_categories = les top_n categories qui passent le prefix-match test.

    Si aucun match prefix -> retourne [] dans valid_categories.
    """
    collection = collection or settings.TYPESENSE_COLLECTION
    top_n = top_n or settings.CAT_FILTER_TOP_N

    params = {
        "collection": collection,
        "q": query,
        "query_by": "categorie",
        "per_page": 1,
        "facet_by": "categorie",
        "max_facet_values": top_n,
        "typo_tokens_threshold": 2,
    }
    try:
        res = typesense_client.multi_search({"searches": [params]})
        result = res["results"][0]
    except Exception as e:
        logger.warning("detect_categories error: %s", e)
        return None, 0.0, []

    facets = result.get("facet_counts", [])
    if not facets:
        return None, 0.0, []

    counts = facets[0].get("counts", [])
    if not counts:
        return None, 0.0, []

    total = sum(c["count"] for c in counts) or 1
    top_cats = [c["value"] for c in counts]
    q_tokens = tokenize(query)
    valid = [c for c in top_cats if is_prefix_match(q_tokens, c, settings.CAT_PREFIX_LOOKAHEAD)]
    confidence = counts[0]["count"] / total
    return counts[0]["value"], confidence, valid
