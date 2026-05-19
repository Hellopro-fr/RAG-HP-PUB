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
from itertools import product
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


def _extract_tokens(cat_name: str, keep_stopwords: bool) -> List[str]:
    """
    Retourne les tokens d'une categorie normalises, dans l'ordre.

    keep_stopwords = False : ne garde que les tokens porteurs (comme avant).
      "Mini-pelles (moins de 10 tonnes)" -> ["mini", "pelles"]
    keep_stopwords = True  : garde tous les tokens (utile pour matcher
      les concatenations utilisateur type "fauteuildebureau").
      "Fauteuil de bureau"  -> ["fauteuil", "de", "bureau"]

    Filtre len >= 2 dans les deux cas pour eviter les artefacts d'apostrophes
    (ex: "Cartouches d'encre" -> token "d" isole -> deviendrait "ds" apres
    pluralization, polluant le synonyme).
    """
    norm = _normalize(cat_name)
    # Supprime tout ce qui est entre parentheses (specs techniques).
    norm = re.sub(r"\([^)]*\)", " ", norm)
    raw = re.findall(r"[a-z0-9]+", norm)
    if keep_stopwords:
        # FIX (PR #550) : len >= 2 au lieu de >= 1 pour eviter "d" -> "ds"
        return [t for t in raw if len(t) >= 2 and not t.isdigit()]
    return [
        t for t in raw
        if len(t) >= 2 and t not in _STOPWORDS_FR and not t.isdigit()
    ]


def _sing_plur_forms(token: str, is_stopword: bool = False) -> List[str]:
    """
    Retourne le token + ses variantes singulier/pluriel (heuristique FR).
    Utilise pour couvrir les cas "minipelle" (singulier) vs "Mini-pelles"
    (pluriel dans le nom de categorie).

    FIX (PR #550) : si is_stopword=True, retourne [token] sans pluralization.
    Evite les artefacts type "et" -> "ets", "pour" -> "pours", "de" -> "des"
    qui generent des synonymes invalides "cable ets adaptateur",
    "support pours ecran", "table des travail", etc.
    """
    if is_stopword:
        return [token]
    forms = {token}
    # pluriel -> singulier
    if token.endswith("aux") and len(token) >= 5:
        # journaux -> journal, generaux -> general
        forms.add(token[:-3] + "al")
    elif token.endswith("eux") and len(token) >= 4:
        # cheveux -> cheveu
        forms.add(token[:-1])
    elif token.endswith("x") and len(token) >= 3:
        # choux -> chou, bijoux -> bijou
        forms.add(token[:-1])
    elif token.endswith("s") and len(token) >= 3 and not token.endswith("ss"):
        # pelles -> pelle, chaussures -> chaussure
        forms.add(token[:-1])
    else:
        # singulier -> pluriel (simple ajout de 's')
        forms.add(token + "s")
    # Garde uniquement ceux de longueur >= 2
    return [f for f in forms if len(f) >= 2]


def _build_variants(tokens: List[str]) -> Set[str]:
    """
    Pour des tokens donnes (ex: ["mini","pelles"]), genere toutes les
    variantes orthographiques utilisateur :
      - 3 separateurs : concatenation, espace, tiret
      - toutes les combinaisons singulier/pluriel de chaque token

    Ex "mini pelles" :
      - ["mini","pelles"]   -> minipelles, mini pelles, mini-pelles
      - ["minis","pelles"]  -> minispelles, minis pelles, minis-pelles
      - ["mini","pelle"]    -> minipelle, mini pelle, mini-pelle    <- AJOUTE
      - ["minis","pelle"]   -> minispelle, minis pelle, minis-pelle

    Pour 1 token seul (ex: "Tractopelles"), on genere juste ses formes
    singulier/pluriel (utile pour query "tractopelle").

    Cap a 4 tokens porteurs pour eviter l'explosion combinatoire.
    """
    if not tokens or len(tokens) > 4:
        return set()

    # Pour chaque token, ses formes s/p
    # FIX (PR #550) : ne pluralise pas les stopwords FR (et, pour, de, ...)
    # pour eviter des variantes parasites du type "cable ets adaptateur"
    # ("et" -> "ets") ou "support pours ecran" ("pour" -> "pours").
    token_forms = [
        _sing_plur_forms(t, is_stopword=(t in _STOPWORDS_FR))
        for t in tokens
    ]

    variants: Set[str] = set()
    for combo in product(*token_forms):
        if len(combo) == 1:
            # 1 mot : pas de separateur, juste la forme
            variants.add(combo[0])
        else:
            variants.add("".join(combo))
            variants.add(" ".join(combo))
            variants.add("-".join(combo))

    # Cap de securite : pas plus de 32 variantes par categorie
    # (4 tokens x 2 formes x 3 separateurs = 48 theorique, mais en pratique
    # beaucoup sont deja dedupliques).
    return {v for v in variants if len(v) >= 4}


def _build_all_variants(cat_name: str) -> Set[str]:
    """
    Genere TOUTES les variantes pour une categorie :
      1. Avec tokens porteurs uniquement (retire stopwords) : "mini pelles"
      2. Avec TOUS les tokens (stopwords inclus) : "mini pelles moins"
         -> sert surtout pour la concatenation "fauteuildebureau".

    L'utilisateur peut taper aussi bien "fauteuilbureau" que
    "fauteuildebureau" -> les deux doivent ramener la categorie.
    """
    core_tokens = _extract_tokens(cat_name, keep_stopwords=False)
    full_tokens = _extract_tokens(cat_name, keep_stopwords=True)

    variants = _build_variants(core_tokens)

    # Ajoute variantes avec stopwords SI le set de tokens est different
    # (= la categorie contient des stopwords entre les mots porteurs).
    if full_tokens != core_tokens and len(full_tokens) <= 5:
        variants |= _build_variants(full_tokens)

    return variants


def _slug_id(s: str) -> str:
    """Transforme une string en id stable pour Typesense (alphanum + tirets)."""
    s = _normalize(s)
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:128] or "auto"


def _list_categories(collection: str) -> List[str]:
    """
    Retourne la liste des noms de categories distincts dans la collection
    via un facet query 'match all'. Cap a 5000 categories (HelloPro tourne
    autour de 8300 rubriques en BDD mais toutes ne sont pas ingerees, et
    Typesense produits_prod en contient ~3100 actuellement).

    Note : max_facet_values Typesense est plafonne a 10000 cote serveur
    (facet_values_max_count), 5000 laisse une marge x2 pour la croissance
    sans degrader les perfs (facet sur 1.5M docs ~ 50-100ms).
    """
    params = {
        "collection": collection,
        "q": "*",
        "query_by": "categorie",
        "per_page": 1,
        "facet_by": "categorie",
        "max_facet_values": 5000,
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
        variants = _build_all_variants(cat)
        if not variants:
            continue  # Categorie trop longue ou vide apres normalisation
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
