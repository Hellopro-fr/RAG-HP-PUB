"""
Charge le dictionnaire IDF (inverse document frequency) calcule offline sur
les nom_produit du catalogue Typesense.

Source : `app/data/idf_nom_produit.json` (genere par `scripts/compute_idf.py`).

Pourquoi : le reranker actuel compte les tokens query matches dans nom_produit
avec un poids uniforme (ratio simple). Sur des queries combinatoires comme
"melangeur conique", "conique" est rare dans le catalogue et plus discriminant
que "melangeur" (commun). En ponderant chaque token par son IDF, on favorise
les produits qui contiennent le token rare, ce qui resout les regressions de
l'audit v3 sur "melangeurs coniques" (2.6/10).

Comportement si le fichier JSON est absent : `idf_available()` retourne False
et le reranker bascule sur le ratio simple (backward-compat, aucun risque de
regression a la mise en prod avant generation du fichier).
"""
import json
import logging
import math
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)


# Chemin par defaut du fichier IDF pre-calcule. Genere via :
#   python scripts/compute_idf.py
# Le fichier est gitignore (~1-5 MB, depend du catalogue live).
_IDF_PATH = Path(__file__).resolve().parent.parent / "data" / "idf_nom_produit.json"


# Etat global du loader (singleton, charge a la 1ere lecture)
_idf_cache: Optional[Dict[str, float]] = None
_idf_median: float = 1.0
_load_attempted: bool = False


def _compute_median(values) -> float:
    """Mediane sans depend de numpy/statistics (~10ms sur 100k tokens)."""
    if not values:
        return 1.0
    vals = sorted(values)
    n = len(vals)
    if n % 2 == 1:
        return vals[n // 2]
    return (vals[n // 2 - 1] + vals[n // 2]) / 2


def _load_idf() -> Dict[str, float]:
    """
    Charge le dict IDF depuis le JSON (cache en RAM).
    Retourne dict vide si fichier absent ou parse error (fallback safe).
    """
    global _idf_cache, _idf_median, _load_attempted

    if _idf_cache is not None:
        return _idf_cache
    if _load_attempted:
        return _idf_cache or {}
    _load_attempted = True

    if not _IDF_PATH.exists():
        logger.warning(
            "IDF file not found at %s - reranker will fallback to flat name_match (ratio simple). "
            "Run `python scripts/compute_idf.py` to generate.",
            _IDF_PATH,
        )
        _idf_cache = {}
        return _idf_cache

    try:
        with open(_IDF_PATH, encoding="utf-8") as f:
            data = json.load(f)

        # Format attendu : {"idf": {"token": float, ...}, "median": float, "n_docs": int}
        # Tolere aussi un format flat {"token": float, ...} pour compat eventuelle.
        if isinstance(data, dict) and "idf" in data and isinstance(data["idf"], dict):
            idf_dict = data["idf"]
            _idf_median = float(data.get("median") or _compute_median(idf_dict.values()))
            n_docs = data.get("n_docs", "?")
            logger.info(
                "IDF loaded from %s : %d tokens, median=%.3f, n_docs=%s",
                _IDF_PATH.name, len(idf_dict), _idf_median, n_docs,
            )
        elif isinstance(data, dict):
            idf_dict = data
            _idf_median = _compute_median(idf_dict.values())
            logger.info(
                "IDF loaded (flat format) from %s : %d tokens, median=%.3f",
                _IDF_PATH.name, len(idf_dict), _idf_median,
            )
        else:
            logger.error("IDF file %s has unexpected format (not a dict) - falling back", _IDF_PATH)
            idf_dict = {}

        _idf_cache = idf_dict
    except (OSError, json.JSONDecodeError) as e:
        logger.exception("Failed to load IDF file %s: %s - fallback to flat name_match", _IDF_PATH, e)
        _idf_cache = {}

    return _idf_cache


def get_idf(token: str) -> float:
    """
    Retourne l'IDF d'un token. Tokens inconnus -> mediane (= token plutot rare,
    pas penalise comme token frequent).
    """
    idf = _load_idf()
    return idf.get(token, _idf_median)


def idf_available() -> bool:
    """True si le dict IDF est charge et non vide (= le reranker peut ponderer)."""
    return bool(_load_idf())


def reset_cache_for_test():
    """Helper pour les tests unitaires : force le rechargement au prochain get_idf."""
    global _idf_cache, _idf_median, _load_attempted
    _idf_cache = None
    _idf_median = 1.0
    _load_attempted = False
