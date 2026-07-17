"""
synonyms_loader.py
==================
Charge les synonymes Typesense au runtime pour expand les query tokens
dans le reranker. Permet le matching multilingue (crane=grue, screen=ecran)
et les variantes (medical/medicale/medicaux) sans avoir a hardcoder.

Pourquoi :
  Typesense applique deja les synonymes au niveau de la recherche (le
  multi_search retourne les Grues XCMG quand on cherche "crane"). MAIS le
  reranker Python recalcule `name_match` en mode texte strict :
  tokens query = {"crane"}, doc "Grue XCMG" = {"grue","xcmg"} -> intersection
  vide -> name_match = 0 -> reranker remonte d'autres produits hors-sujet.

  Avec ce loader, le reranker connait aussi les equivalences. Pour la query
  "crane", il calcule name_match comme si l'utilisateur avait tape "crane OU
  grue OU grues OU grutier" -> le doc "Grue XCMG" matche "grue" -> covered.

Comportement si Typesense indisponible : `get_synonyms_map()` retourne
{} et le reranker bascule sur le matching strict (= comportement A4 actuel,
sans regression).
"""
import logging
from typing import Dict, Set, Optional

from app.core.credentials import settings
from app.core.typesense_client import typesense_client
from app.utils.text import tokenize

logger = logging.getLogger(__name__)


# Etat global (singleton charge a la 1ere demande, cache en RAM jusqu'au restart)
_syn_map: Optional[Dict[str, Set[str]]] = None
_load_attempted: bool = False


def _build_mapping_from_clusters(clusters) -> Dict[str, Set[str]]:
    """
    A partir des clusters synonymes Typesense, construit un dict :
      token -> set de tokens equivalents (incluant le token lui-meme).

    Tokenise/normalise les synonymes via `tokenize()` (meme regex que le
    reranker), pour garantir un alignement parfait (accents, casse,
    multi-mots, longueur min 2 chars).

    Exemple cluster :
      {"synonyms": ["grue", "grues", "grutier", "crane", "cranes", "e-crane"]}
    -> apres tokenize : {"grue", "grues", "grutier", "crane", "cranes"}
       (le "e" de "e-crane" est filtre car < 2 chars)
    -> mapping construit :
       {
         "grue":    {"grue","grues","grutier","crane","cranes"},
         "grues":   {idem},
         "grutier": {idem},
         "crane":   {idem},
         "cranes":  {idem},
       }
    """
    mapping: Dict[str, Set[str]] = {}
    if not clusters:
        return mapping

    for cluster in clusters:
        if not isinstance(cluster, dict):
            continue
        syns = cluster.get("synonyms") or []
        if not syns:
            continue

        # Tokenise et fusionne en un seul set de tokens pour ce cluster
        cluster_tokens: Set[str] = set()
        for syn in syns:
            cluster_tokens |= tokenize(syn)
        # Inclut aussi le "root" si fourni (one-way synonym)
        root = cluster.get("root")
        if root:
            cluster_tokens |= tokenize(root)

        if not cluster_tokens:
            continue

        # Pour chaque token du cluster, l'associer au set complet d'equivalents
        for t in cluster_tokens:
            if t not in mapping:
                mapping[t] = set()
            mapping[t] |= cluster_tokens  # union (inclut soi-meme, no-op)

    return mapping


def _load_synonyms() -> Dict[str, Set[str]]:
    """
    Charge le mapping synonymes une seule fois (cache singleton).
    Fallback safe si Typesense indisponible ou collection sans synonymes.
    """
    global _syn_map, _load_attempted

    if _syn_map is not None:
        return _syn_map
    if _load_attempted:
        return _syn_map or {}
    _load_attempted = True

    try:
        res = typesense_client.list_synonyms()
        clusters = res.get("synonyms", []) if isinstance(res, dict) else []
        mapping = _build_mapping_from_clusters(clusters)
        _syn_map = mapping

        # Stats utiles dans les logs (visibles au demarrage du service apres la 1ere recherche)
        n_clusters = len(clusters)
        n_tokens = len(mapping)
        if n_tokens > 0:
            n_avg = sum(len(v) for v in mapping.values()) / n_tokens
            logger.info(
                "Synonyms loaded from Typesense: %d clusters, %d unique tokens, avg %.1f equivalents/token",
                n_clusters, n_tokens, n_avg,
            )
        else:
            logger.warning(
                "Synonyms loaded from Typesense but mapping is empty (%d clusters returned, 0 tokens after tokenize)",
                n_clusters,
            )
    except Exception as e:
        logger.warning(
            "Failed to load synonyms from Typesense (%s) - reranker will skip token expansion",
            e,
        )
        _syn_map = {}

    return _syn_map


def get_synonyms_map() -> Dict[str, Set[str]]:
    """
    Retourne le mapping token -> set d'equivalents.
    {} si Typesense indisponible ou pas de synonymes (fallback safe).
    """
    return _load_synonyms()


def synonyms_available() -> bool:
    """True si des synonymes sont charges (i.e. mapping non vide)."""
    return bool(_load_synonyms())


def expand_tokens(q_tokens: Set[str]) -> Set[str]:
    """
    Helper : expand un set de tokens query avec leurs synonymes.
    Ex : expand_tokens({"crane"}) -> {"crane", "grue", "grues", "grutier", "cranes"}

    Note : le reranker n'utilise PAS cette fonction directement (il prefere
    appeler _idf_weighted_match avec syn_map pour preserver le denominateur IDF
    base sur les tokens ORIGINAUX). Elle est exposee pour usage externe / tests.
    """
    syn_map = _load_synonyms()
    if not syn_map:
        return set(q_tokens)

    expanded = set(q_tokens)
    for t in q_tokens:
        equivs = syn_map.get(t)
        if equivs:
            expanded |= equivs
    return expanded


def reset_cache_for_test():
    """Helper tests unitaires : force le rechargement au prochain appel."""
    global _syn_map, _load_attempted
    _syn_map = None
    _load_attempted = False
