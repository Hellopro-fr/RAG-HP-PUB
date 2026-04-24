"""
Synonyms service : auto-generation des synonymes Typesense pour les mots
composes (compound words) et variantes tiret / espace / concatenation.

Contexte :
Typesense BM25 est token-exact : il ne matchera pas "minipelle" (1 token)
contre "Mini-pelles" (tokens "mini", "pelles" apres split sur le tiret).
La solution generique : scanner TOUS les noms de categories ingerees et
generer automatiquement pour chacun les 3 variantes equivalentes :

  "Mini-pelles (moins de 10 tonnes)"
    -> base tokens : ["mini", "pelles"]
    -> variantes   : "minipelles" (concat), "mini pelles" (espace), "mini-pelles" (tiret)
    -> synonyme multi-way : toute query avec l'une de ces formes remonte les autres.

Ainsi, pour n'importe quelle categorie future (Tractopelle, Microtracteur,
Electrogene, etc.) dont le nom contient au moins un mot compose (tokens
separes par tiret OU par espace), on couvre toutes les variantes
d'ecriture utilisateur sans maintenance manuelle de liste metier.

A appeler :
  - une fois apres ingestion initiale
  - apres chaque ingestion batch de nouvelles categories

via endpoint : POST /admin/synonyms/auto-generate
"""
import logging
import re
import unicodedata
from typing import Dict, List, Any, Optional, Tuple, Set

from app.core.credentials import settings
from app.core.typesense_client import typesense_client

logger = logging.getLogger(__name__)


# Stopwords FR B2B a retirer des noms de categorie avant de generer les
# variantes. Ce ne sont pas des mots porteurs de sens pour la query user.
_STOPWORDS_FR = {
    "de", "du", "la", "le", "les", "des", "un", "une", "et", "ou", "a", "au",
    "aux", "en", "dans", "pour", "par", "avec", "sans", "sur", "sous", "entre",
    "moins", "plus", "tonnes", "tonne", "kg", "mm", "cm", "m", "kw", "kva",
    "litres", "litre", "l", "ans", "an", "heures", "heure", "h",
}
# Nombres et tokens purement numeriques -> a retirer aussi (pas discriminants
# pour la query "minipelle" vs "Mini-pelles (moins de 10 tonnes)").


def _normalize(s: str) -> str:
    """Retire accents + lowercase."""
    if not s:
        return ""
    s = unicodedata.normalize("NFD", s)
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower()


def _extract_meaningful_tokens(cat_name: str) -> List[str]:
    """
    Retourne les tokens 'porteurs' d'une categorie, normalises, dans l'ordre.

    Ex :
      "Mini-pelles (moins de 10 tonnes)"
        -> ["mini", "pelles"]                 (retire 'moins','de','10','tonnes')
      "Groupe electrogene industriel"
        -> ["groupe", "electrogene", "industriel"]
      "Tractopelles"
        -> ["tractopelles"]
      "Pelle rail-route"
        -> ["pelle", "rail", "route"]
    """
    norm = _normalize(cat_name)
    # Supprime tout ce qui est entre parentheses (specs techniques).
    norm = re.sub(r"\([^)]*\)", " ", norm)
    # Tokenise sur [a-z0-9]+ puis garde >=2 chars et pas dans stopwords,
    # et pas purement numerique.
    raw = re.findall(r"[a-z0-9]+", norm)
    return [
        t for t in raw
        if len(t) >= 2 and t not in _STOPWORDS_FR and not t.isdigit()
    ]


def _build_variants(tokens: List[str]) -> Set[str]:
    """
    Genere les variantes orthographiques equivalentes a partir des tokens :
      - concatenation (sans separateur) : "minipelles"
      - join par espace                 : "mini pelles"
      - join par tiret                  : "mini-pelles"

    Si le nom ne contient qu'UN seul token (ex: "Tractopelles"), il n'y a
    pas de compound-word possible -> retourne set vide (pas de synonyme
    utile a creer).

    Si le nom contient plus de 4 tokens, on ne genere pas non plus : au
    dela c'est un nom long type "Remorques a ridelles basculantes" et
    l'utilisateur ne les concatene jamais.
    """
    if len(tokens) < 2 or len(tokens) > 4:
        return set()
    variants = {
        "".join(tokens),
        " ".join(tokens),
        "-".join(tokens),
    }
    # Filtre : on ne garde que si les variantes sont reellement differentes
    # et contiennent au moins 4 chars.
    return {v for v in variants if len(v) >= 4}


def _slug_id(s: str) -> str:
    """Transforme une string en id stable pour Typesense (alphanum + tirets)."""
    s = _normalize(s)
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:128] or "auto"


def _list_categories(collection: str) -> List[str]:
    """
    Retourne la liste des noms de categories distincts dans la collection
    via un facet query 'match all'. Cap a 2000 categories (HelloPro tourne
    autour de 8300 rubriques en BDD mais toutes ne sont pas ingerees).
    """
    params = {
        "collection": collection,
        "q": "*",
        "query_by": "categorie",
        "per_page": 1,
        "facet_by": "categorie",
        "max_facet_values": 2000,
    }
    try:
        res = typesense_client.multi_search({"searches": [params]})
        result = res["results"][0]
    except Exception as e:
        logger.error("list_categories error: %s", e)
        return []
    facets = result.get("facet_counts", [])
    if not facets:
        return []
    counts = facets[0].get("counts", [])
    return [c["value"] for c in counts if c.get("value")]


def auto_generate_synonyms(
    collection: Optional[str] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Scan toutes les categories de la collection, genere les variantes
    compound-words, et les enregistre comme synonymes multi-way Typesense.

    Retourne un dict de stats :
      {
        "nb_categories": int,
        "nb_synonyms_generated": int,    # categories eligibles (multi-tokens)
        "nb_synonyms_pushed": int,       # effectivement PUT dans Typesense
        "nb_errors": int,
        "examples": [{"cat":..., "variants":[...]}],   # 10 premiers
        "errors": [{"cat":..., "error":...}],
        "dry_run": bool,
      }

    dry_run=True : calcule les synonymes mais ne les push pas (utile pour
    revue avant activation).
    """
    collection = collection or settings.TYPESENSE_COLLECTION
    cats = _list_categories(collection)
    nb_generated = 0
    nb_pushed = 0
    errors: List[Dict[str, str]] = []
    examples: List[Dict[str, Any]] = []

    for cat in cats:
        tokens = _extract_meaningful_tokens(cat)
        variants = _build_variants(tokens)
        if not variants:
            continue  # 1 token seul ou trop long -> pas de compound utile
        nb_generated += 1

        syn_id = "auto-" + _slug_id(cat)
        if len(examples) < 10:
            examples.append({"cat": cat, "variants": sorted(variants)})

        if dry_run:
            continue

        try:
            typesense_client.upsert_synonym(
                synonym_id=syn_id,
                synonyms=sorted(variants),
                root=None,
                collection=collection,
            )
            nb_pushed += 1
        except Exception as e:
            errors.append({"cat": cat, "error": str(e)})

    return {
        "nb_categories": len(cats),
        "nb_synonyms_generated": nb_generated,
        "nb_synonyms_pushed": nb_pushed,
        "nb_errors": len(errors),
        "examples": examples,
        "errors": errors[:20],
        "dry_run": dry_run,
    }
