"""
Pont vers le service de normalisation HISTORIQUE (source de vérité du seed).

Le seed et le test de parité s'appuient sur les données du service
`graph-rag-normalize-unite-service` :
  - les 3 dictionnaires (UNIT_TO_DIMENSION / LABEL_TO_DIMENSION / CANONICAL_UNITS)
    sont extraits dynamiquement de son instance singleton (zéro recopie → zéro dérive) ;
  - la liste ORDONNÉE des pint define() ne vit que sous forme d'appels `ureg.define(...)`
    dans son `__new__` : impossible à extraire de l'instance, donc copiée verbatim
    ci-dessous dans le MÊME ORDRE (les définitions dépendent les unes des autres).

Le test de parité valide que cette copie est fidèle : un define manquant ou
mal ordonné ferait diverger une conversion → assertion en échec.
"""

import importlib.util
from pathlib import Path
from typing import Any, Dict

# --- pint define() du service historique, copiés VERBATIM dans l'ordre de __new__ ---
PINT_DEFINITIONS = [
    "unité = count = unite = Nb = nb",
    "pieds = foot = pied",
    "decibel = [sound] = dB = dBA",
    "cheval = 735.49875 * watt = ch",
    "chevaux = count",
    "segments = count = segment",
    "mètres = meter",
    "Litres = liter",
    "Volts = volt",
    "sélections = count = selections = selection = sélection",
    "galettes = count = galette = Galettes = Galette",
    "tasses_par_jour = count",
    "Watts = watt",
    "unités = count",
    "billets = count = billet",
    "pièces = count = pièce",
    "personnes = count = personne",
    "degré = degree = degre = degrés = degres",
    "Tonnes = tonne",
    "démarrages = count = démarrage",
    "lignes = count = ligne",
    "tours_par_minute_fr = revolutions_per_minute",
    "pouces = 0.0254 * meter = pouce = inch_fr",
    "semelles_unit = count = semelles = semelle",
    "plots_unit = count = plots = plot",
    "bacs_unit = count = bacs = bac",
    "vehicules_unit = count = vehicules = vehicule",
    "recettes_par_programme = count",
    "coups_par_minute = count / minute",
    "coupes_par_minute = count / minute",
    "tonne = 1000 * kilogram = t",
    "mm = millimeter",
    "cm = centimeter",
    "m = meter",
    "kg = kilogram",
    "KW = 1000 * watt",
    "kw = 1000 * watt",
    "cheval_vapeur = 735.49875 * watt = cv",
    "CV = cheval_vapeur",
    "V = volt",
    "A = ampere",
    "sec = second",
    "ph = hertz",
    "tours_par_minute = revolutions_per_minute = rpm = tr/min = trs/min",
    "Pa = pascal",
    "kPa = 1000 * pascal",
    "L_par_min = liter / minute = l/min",
    "L_par_h = liter / hour = l/h",
    "m3_par_h = meter**3 / hour",
    "m3 = meter**3",
    "litres = liter",
    "L = liter",
    "N = newton",
    "kgf = 9.80665 * newton",
    "Nm = newton * meter",
    "kg_par_m2 = kilogram / meter ** 2 = kg/m² = kg/m2",
]

# --- Transforms universels (ordonnés, avec phase) — reprend NFKC/parens/middledot/superscripts ---
# pre_snapshot : avant le snapshot original_unit (sert au lookup dimension)
# post_snapshot : après (sert à l'expression pint)
PREPROCESSING_RULES = [
    {"type": "nfkc",        "phase": "pre_snapshot",  "pattern": None,                  "remplacement": "", "ordre": 0},
    {"type": "regex_sub",   "phase": "pre_snapshot",  "pattern": r"\s*\([^)]*\)\s*$",   "remplacement": "", "ordre": 1},
    {"type": "str_replace", "phase": "pre_snapshot",  "pattern": "·",                   "remplacement": ".", "ordre": 2},
    {"type": "str_replace", "phase": "post_snapshot", "pattern": "³",                   "remplacement": "3", "ordre": 3},
    {"type": "str_replace", "phase": "post_snapshot", "pattern": "²",                   "remplacement": "2", "ordre": 4},
]

# --- Réécritures exactes (clé minuscule -> expr pint), ou bypass (-> unité canonique directe) ---
# Reprend les branches du if/elif de normalize() (hors désambiguïsation par label).
# (source, kind, value) ; kind ∈ {'rewrite','bypass'}.
_REWRITE_TUPLES = [
    ("db(a)", "rewrite", "dBA"),
    ("tr/min", "rewrite", "rpm"),
    ("trs/min", "rewrite", "rpm"),
    ("m3/h", "rewrite", "m**3 / hour"),
    ("m2", "rewrite", "m**2"),
    ("m3", "rewrite", "m**3"),
    ("kg/m2", "rewrite", "kilogram / meter ** 2"),
    ("kg/m3", "rewrite", "kilogram / meter ** 3"),
    ("g/min", "rewrite", "gram / minute"),
    ("pièces/seconde", "rewrite", "count / second"),
    ("pieces/seconde", "rewrite", "count / second"),
    ("billets/seconde", "rewrite", "count / second"),
    ("tasses/jour", "rewrite", "count"),
    ("watts", "rewrite", "watt"),
    ("kwh/24h", "rewrite", "kilowatt_hour / day"),
    ("l/cycle", "rewrite", "liter"),
    ("tonnes", "rewrite", "tonne"),
    ("pieds", "rewrite", "pieds"),
    ("pied", "rewrite", "pieds"),
    ("démarrages/heure", "rewrite", "1 / hour"),
    ("tours/min", "rewrite", "rpm"),
    ("tour/min", "rewrite", "rpm"),
    ("lignes", "rewrite", "count"),
    ("ligne", "rewrite", "count"),
    ("pouces", "rewrite", "inch"),
    ("pouce", "rewrite", "inch"),
    ("km/h", "rewrite", "kilometer / hour"),
    ("lm/w", "rewrite", "lumen / watt"),
    ("%", "bypass", "count"),
    ("ra", "bypass", "count"),
    ("minutes", "rewrite", "minute"),
    ("μm", "rewrite", "micrometer"),  # Greek mu U+03BC (forme NFKC)
    ("kg/24h", "rewrite", "kilogram / day"),
    ("m2/h", "rewrite", "meter ** 2 / hour"),
    ("w/m2.k", "rewrite", "watt / (meter ** 2 * kelvin)"),
    ("m2.k/w", "rewrite", "meter ** 2 * kelvin / watt"),
    ("coups/min", "rewrite", "1 / minute"),
    ("coupes/min", "rewrite", "1 / minute"),
    ("heures", "rewrite", "hour"),
    ("heure", "rewrite", "hour"),
    ("go", "rewrite", "gigabyte"),
    ("mo", "rewrite", "megabyte"),
    ("ko", "rewrite", "kilobyte"),
    ("to", "rewrite", "terabyte"),
    ("mohs", "bypass", "count"),
    ("kn/m2", "rewrite", "kilonewton / meter ** 2"),
    ("cd/m2", "rewrite", "candela / meter ** 2"),
    ("ah", "rewrite", "ampere_hour"),
    ("a.h", "rewrite", "ampere_hour"),
    ("amperes-heures", "rewrite", "ampere_hour"),
    ("ampere-heure", "rewrite", "ampere_hour"),
    ("ampères-heures", "rewrite", "ampere_hour"),
    ("ampère-heure", "rewrite", "ampere_hour"),
    ("mah", "rewrite", "milliampere_hour"),
    ("kilogrammes", "rewrite", "kilogram"),
    ("kilogramme", "rewrite", "kilogram"),
    ("grammes", "rewrite", "gram"),
    ("gramme", "rewrite", "gram"),
    ("millimètres", "rewrite", "millimeter"),
    ("millimètre", "rewrite", "millimeter"),
    ("centimètres", "rewrite", "centimeter"),
    ("centimètre", "rewrite", "centimeter"),
    ("décibels", "rewrite", "decibel"),
    ("décibel", "rewrite", "decibel"),
    ("decibels", "rewrite", "decibel"),
    ("decibel", "rewrite", "decibel"),
    ("cycles/jour", "rewrite", "1 / day"),
    ("cycles / jour", "rewrite", "1 / day"),
    ("kwh/kg", "rewrite", "kilowatt_hour / kilogram"),
    ("kwh / kg", "rewrite", "kilowatt_hour / kilogram"),
    ("kwc", "rewrite", "kilowatt"),
    ("mpa.s", "rewrite", "millipascal * second"),
    ("pa.s", "rewrite", "pascal * second"),
    ("cycles par jour", "rewrite", "1 / day"),
    ("secondes", "rewrite", "second"),
    ("seconde", "rewrite", "second"),
]
REWRITE_RULES = [
    {"unite_source": src, "kind": kind, "value": value} for src, kind, value in _REWRITE_TUPLES
]

# NB : la désambiguïsation (nm / t/min / G) reste STATIQUE dans le code du moteur
# (unit_normalization_service._STATIC_DISAMBIGUATIONS) — pas seedée en base.

_OLD_SERVICE_FILE = (
    Path(__file__).resolve().parents[2]
    / "graph-rag-normalize-unite-service"
    / "infrastructure"
    / "unit_normalization_service.py"
)


def load_legacy_normalizer():
    """Charge l'instance singleton `unit_normalizer` du service historique par chemin de fichier.

    On évite un import classique : le module porte le même nom que celui du service
    dynamique (`infrastructure.unit_normalization_service`) → collision de namespace.
    importlib avec un nom dédié contourne le problème.
    """
    spec = importlib.util.spec_from_file_location(
        "legacy_unit_normalization_service", _OLD_SERVICE_FILE
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.unit_normalizer


def build_legacy_payload() -> Dict[str, Any]:
    """Construit le payload au format BO v2 `referentiel/get` à partir du service historique."""
    old = load_legacy_normalizer()
    return {
        "definitions": [
            {"definition": d, "ordre": i} for i, d in enumerate(PINT_DEFINITIONS)
        ],
        "unite_dimension": [
            {"unite": k, "dimension": v} for k, v in old.UNIT_TO_DIMENSION.items()
        ],
        "label_dimension": [
            {"label": k, "dimension": v, "priorite": i}
            for i, (k, v) in enumerate(old.LABEL_TO_DIMENSION.items())
        ],
        "dimension_canonique": [
            {"dimension": k, "unite_canonique": v} for k, v in old.CANONICAL_UNITS.items()
        ],
        "preprocessing": PREPROCESSING_RULES,
        "reecriture": REWRITE_RULES,
    }


# =====================================================================
# Simulations des 2 GET backend (pour les tests bout-en-bout / symbiose).
# On SUPPOSE que le BO (normalisation.php) renverra exactement ces structures :
#   - get_referentiel_normalisation()  -> simulate_get_referentiel_normalisation()
#   - get_apprentissage_unite()        -> simulate_get_apprentissage_unite()
# =====================================================================

def simulate_get_referentiel_normalisation() -> Dict[str, Any]:
    """Simule la réponse de `normalisation/referentiel/get` (BO) = référentiel seedé complet."""
    return build_legacy_payload()


# Données test d'apprentissage : unités déjà traitées lors d'un run précédent (dédup inter-run).
# Clé = (unite_minuscule, label_context). Statuts terminaux → le learner saute (pas de re-LLM).
FAKE_APPRENTISSAGE = {
    ("nm", ""): {
        "statut": "learned", "confiance": 1.0, "nb_occurrences": 3, "nb_requeue": 0,
        "payload_llm": None, "raison_rejet": None,
    },
    ("furlong", ""): {
        "statut": "rejected", "confiance": 0.4, "nb_occurrences": 1, "nb_requeue": 0,
        "payload_llm": None, "raison_rejet": "validation NOK",
    },
}


def simulate_get_apprentissage_unite(unite, label_context=""):
    """Simule `normalisation/apprentissage/get` (BO) : retourne la ligne test ou None (jamais vu)."""
    key = (str(unite).strip().lower(), str(label_context or "").strip())
    return FAKE_APPRENTISSAGE.get(key)
