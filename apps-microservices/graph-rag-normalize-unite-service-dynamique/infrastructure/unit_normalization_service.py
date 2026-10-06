"""
Moteur de normalisation d'unités — version DYNAMIQUE, 100 % piloté par référentiel.

Aucune unité n'est codée en dur : mappings, alias pint, transforms universels,
réécritures et désambiguïsations proviennent tous du `Referentiel` (chargé depuis
le BO v2, rechargeable à chaud). Le code ne contient que l'INTERPRÉTEUR générique.

Pipeline de `normalize()` (équivalent sémantique à l'ancien if/elif, mais data-driven) :
  1. Parsing valeur (tolère '+/- 2', '±').
  2. Preprocessing phase 'pre_snapshot' (NFKC, strip parens, ·→.) -> `original_unit`.
  3. Preprocessing phase 'post_snapshot' (³→3, ²→2) -> base de l'expression pint.
  4. Désambiguïsation par label (nm / t/min / G…) : peut imposer un bypass, une
     expression pint, et/ou une dimension.
  5. Réécriture exacte (unité->expr pint, ou bypass->canonique).
  6. Résolution de dimension : override désambiguïsation, sinon unité, sinon label.
  7. Bypass pour count/count_rate.
  8. Conversion pint vers l'unité canonique.

Concurrence : `_NormalizerState` immuable ; `UnitNormalizationService.reload()` swap
la référence sous lock ; lecture lock-free (snapshot de référence atomique).
"""

import logging
import re
import threading
import unicodedata
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from pint import UnitRegistry

from infrastructure.referentiel_loader import Referentiel

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _PreprocStep:
    """Étape de preprocessing VALIDÉE/COMPILÉE au build → ne peut plus lever au runtime.
    `pattern` : str (str_replace) | re.Pattern compilé (regex_sub) | None (nfkc)."""
    phase: str
    type: str
    pattern: Any = None
    remplacement: str = ""


@dataclass(frozen=True)
class _Disambiguation:
    """Override conditionnel basé sur des mots-clés du label.

    STATIQUE en code (et non en base) : ce ne sont que 3 cas contextuels (nm / t/min / G),
    avec une probabilité d'en ajouter quasi nulle. Les dynamiser en base ajouterait un
    schéma lourd pour un gain inexistant. Si un indicateur ∈ label -> applique
    (dimension_si_match, pint_si_match, bypass_si_match). Sinon -> (dimension_sinon, pint_sinon).
    """
    unite_source: str
    indicateurs: Tuple[str, ...]
    case_sensitive: bool = False
    dimension_si_match: Optional[str] = None
    pint_si_match: Optional[str] = None
    bypass_si_match: Optional[str] = None
    dimension_sinon: Optional[str] = None
    pint_sinon: Optional[str] = None


# Désambiguïsations contextuelles (équivalent aux blocs nm / t/min / G de l'historique).
_STATIC_DISAMBIGUATIONS: Tuple[_Disambiguation, ...] = (
    # 'nm' : nanomètre (length) si le label évoque une longueur, sinon UNIT_TO_DIMENSION['nm'] (torque).
    _Disambiguation(
        unite_source="nm",
        indicateurs=(
            "longueur d'onde", "wavelength", "epaisseur", "diametre", "rayon",
            "distance", "profondeur", "largeur", "hauteur", "longueur",
        ),
        dimension_si_match="length",
    ),
    # 't/min' : tonnes/min (mass_flow) si contexte production, sinon tours/min (rpm).
    _Disambiguation(
        unite_source="t/min",
        indicateurs=("debit", "capacite de production", "production", "consommation", "tonnage"),
        dimension_si_match="mass_flow",
        pint_si_match="tonne / minute",
        pint_sinon="rpm",
    ),
    # 'G' (sensible à la casse) : Facteur G (centrifuge) = ratio sans dimension -> count.
    _Disambiguation(
        unite_source="G",
        indicateurs=("facteur",),
        case_sensitive=True,
        bypass_si_match="count",
    ),
)


class _NormalizerState:
    """État immuable : registre pint + structures du référentiel + interpréteur."""

    def __init__(self, referentiel: Referentiel):
        self.ureg = UnitRegistry()

        # Rejouer les pint define() DANS L'ORDRE (dépendances entre définitions).
        # Un define invalide isolé ne casse pas tout le rebuild : on logge et on continue.
        self.define_errors: List[str] = []
        for definition in referentiel.definitions:
            try:
                self.ureg.define(definition)
            except Exception as exc:
                self.define_errors.append(definition)
                logger.error("pint define() invalide ignoré: '%s' (%s)", definition, exc)

        self.UNIT_TO_DIMENSION: Dict[str, str] = dict(referentiel.unit_to_dimension)
        self.LABEL_TO_DIMENSION = list(referentiel.label_to_dimension)  # ORDONNÉ
        self.CANONICAL_UNITS: Dict[str, str] = dict(referentiel.canonical_units)
        self.REWRITES = dict(referentiel.rewrites)
        # Désambiguïsations : STATIQUES en code (3 cas contextuels, cf. _STATIC_DISAMBIGUATIONS).
        self.DISAMBIGUATIONS: Tuple[_Disambiguation, ...] = _STATIC_DISAMBIGUATIONS

        # Preprocessing : validé + regex compilées AU BUILD (jamais d'erreur runtime).
        # Une règle invalide (regex_sub sans pattern / regex malformée / type inconnu)
        # est ignorée et tracée dans preprocessing_errors (surfacée par reload()).
        self.preprocessing_errors: List[str] = []
        self._preproc_steps: List[_PreprocStep] = []
        for rule in referentiel.preprocessing:  # ORDONNÉ
            if rule.type == "nfkc":
                self._preproc_steps.append(_PreprocStep(rule.phase, "nfkc"))
            elif rule.type == "str_replace":
                if not rule.pattern:
                    self.preprocessing_errors.append(repr(rule))
                    logger.error("Règle str_replace sans pattern ignorée: %r", rule)
                    continue
                self._preproc_steps.append(
                    _PreprocStep(rule.phase, "str_replace", rule.pattern, rule.remplacement)
                )
            elif rule.type == "regex_sub":
                if not rule.pattern:
                    self.preprocessing_errors.append(repr(rule))
                    logger.error("Règle regex_sub sans pattern ignorée: %r", rule)
                    continue
                try:
                    compiled = re.compile(rule.pattern)
                except re.error as exc:
                    self.preprocessing_errors.append(rule.pattern)
                    logger.error("Règle regex_sub invalide ignorée: %r (%s)", rule.pattern, exc)
                    continue
                self._preproc_steps.append(
                    _PreprocStep(rule.phase, "regex_sub", compiled, rule.remplacement)
                )
            else:
                self.preprocessing_errors.append(repr(rule))
                logger.error("Type de preprocessing inconnu ignoré: %r", rule)

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _strip_accents(text: str) -> str:
        if not text:
            return text
        return "".join(
            c for c in unicodedata.normalize("NFKD", text)
            if not unicodedata.combining(c)
        )

    def _apply_preprocessing(self, unit: Optional[str], phase: str) -> Optional[str]:
        """Applique les transforms universels d'une phase, dans l'ordre. None reste None.
        Étapes validées/compilées au build → aucune erreur possible ici."""
        for step in self._preproc_steps:
            if step.phase != phase:
                continue
            if not unit:
                break
            if step.type == "nfkc":
                unit = unicodedata.normalize("NFKC", unit)
            elif step.type == "regex_sub":
                # Sémantique strip-parens d'origine : on ne remplace que si le résultat
                # n'est pas vide (sinon on conserve l'unité telle quelle).
                result = step.pattern.sub(step.remplacement, unit).strip()
                if result:
                    unit = result
            elif step.type == "str_replace":
                unit = unit.replace(step.pattern, step.remplacement)
        return unit

    def _match_disambiguation(
        self, unit: Optional[str], label: str
    ) -> Optional[Dict[str, Optional[str]]]:
        """Retourne l'override désambiguïsation pour l'unité courante, ou None si aucune règle."""
        if not unit:
            return None
        label_norm = self._strip_accents(label.strip().lower()) if label else ""
        for rule in self.DISAMBIGUATIONS:
            current = unit.strip() if rule.case_sensitive else unit.strip().lower()
            target = rule.unite_source if rule.case_sensitive else rule.unite_source.lower()
            if current != target:
                continue
            matched = any(ind in label_norm for ind in rule.indicateurs)
            if matched:
                return {
                    "dimension": rule.dimension_si_match,
                    "pint": rule.pint_si_match,
                    "bypass": rule.bypass_si_match,
                }
            return {
                "dimension": rule.dimension_sinon,
                "pint": rule.pint_sinon,
                "bypass": None,
            }
        return None

    def _get_dimension(self, unit: Optional[str], label: str) -> Optional[str]:
        """Résolution de base : unité exacte (minuscule) puis sous-chaîne du label.
        La désambiguïsation contextuelle (nm/t/min) est gérée en amont par les règles."""
        if unit:
            unit_lower = unit.strip().lower()
            if unit_lower in self.UNIT_TO_DIMENSION:
                return self.UNIT_TO_DIMENSION[unit_lower]
        if label:
            label_norm = self._strip_accents(label.strip().lower())
            for keyword, dimension in self.LABEL_TO_DIMENSION:
                if self._strip_accents(keyword) in label_norm:
                    return dimension
        return None

    # ------------------------------------------------------------------ #
    # Normalisation
    # ------------------------------------------------------------------ #
    def normalize(
        self,
        label: str,
        unit: Optional[str],
        value: Any,
        data_type: Optional[str] = "numeric",
    ) -> Dict[str, Any]:
        if data_type not in ["numeric", "numeric_range"]:
            return {}

        if isinstance(value, str):
            try:
                value_clean = (
                    value.strip().lstrip("+").replace("/-", "").replace("±", "").strip()
                )
                value = float(value_clean)
            except ValueError:
                return {}

        if not all([label, value is not None]):
            return {}

        # 2. Preprocessing pré-snapshot (NFKC, strip parens, ·→.) → original_unit
        unit = self._apply_preprocessing(unit, phase="pre_snapshot")
        original_unit = unit
        # 3. Preprocessing post-snapshot (³→3, ²→2) → base expression pint
        unit = self._apply_preprocessing(unit, phase="post_snapshot")

        # 4. Désambiguïsation par label (peut imposer bypass / pint / dimension)
        disambig = self._match_disambiguation(unit, label)
        if disambig and disambig.get("bypass"):
            return {"valeur_canonique": float(value), "unite_canonique": disambig["bypass"]}

        # 5. Réécriture exacte (rewrite -> expr pint ; bypass -> canonique direct)
        if unit:
            rule = self.REWRITES.get(unit.strip().lower())
            if rule is not None:
                if rule.kind == "bypass":
                    return {"valeur_canonique": float(value), "unite_canonique": rule.value}
                unit = rule.value

        # Override d'expression pint issu de la désambiguïsation (ex. t/min -> tonne/minute|rpm)
        if disambig and disambig.get("pint"):
            unit = disambig["pint"]

        # 6. Dimension : override désambiguïsation sinon résolution unité/label
        dimension = disambig.get("dimension") if disambig else None
        if not dimension:
            dimension = self._get_dimension(original_unit, label)

        # 7. Bypass count / count_rate (pint ne convertit pas ces unités custom)
        if dimension in ("count", "count_rate") and dimension is not None:
            canonical_unit_str = self.CANONICAL_UNITS.get(dimension)
            if canonical_unit_str:
                return {
                    "valeur_canonique": float(value),
                    "unite_canonique": canonical_unit_str,
                }

        if not dimension:
            return {}

        canonical_unit = self.CANONICAL_UNITS.get(dimension)
        if not canonical_unit:
            return {}

        # 8. Conversion pint
        try:
            if unit and unit.lower() != "null":
                quantity = self.ureg.Quantity(value, unit)
                canonical_quantity = quantity.to(canonical_unit)
                magnitude = canonical_quantity.magnitude
                return {
                    "valeur_canonique": float(f"{magnitude:.6g}"),
                    "unite_canonique": str(canonical_quantity.units),
                }
            return {
                "valeur_canonique": float(value),
                "unite_canonique": canonical_unit,
            }
        except Exception as e:
            logging.warning(
                f"Could not normalize unit for label '{label}': value='{value}', unit='{unit}'. Reason: {e}"
            )
            return {}

    def normalize_range(
        self, label: str, unit: Optional[str], min_val: float, max_val: float
    ) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        if min_val is not None:
            norm_min = self.normalize(label, unit, min_val, "numeric")
            if norm_min:
                result["valeur_min_canonique"] = norm_min["valeur_canonique"]
                result["unite_canonique"] = norm_min["unite_canonique"]
        if max_val is not None:
            norm_max = self.normalize(label, unit, max_val, "numeric")
            if norm_max:
                result["valeur_max_canonique"] = norm_max["valeur_canonique"]
                if "unite_canonique" not in result:
                    result["unite_canonique"] = norm_max["unite_canonique"]
        return result


class UnitNormalizationService:
    """Façade thread-safe autour d'un `_NormalizerState` rechargeable.
    Lecture sans lock (snapshot de référence atomique) ; reload sous lock."""

    def __init__(self, referentiel: Referentiel):
        self._lock = threading.Lock()
        self._state = _NormalizerState(referentiel)
        self._referentiel = referentiel  # conservé pour /admin/validate (merge avec proposition)

    def reload(self, referentiel: Referentiel) -> Dict[str, Any]:
        new_state = _NormalizerState(referentiel)
        with self._lock:
            self._state = new_state
            self._referentiel = referentiel
        counts = referentiel.counts()
        counts["define_errors"] = len(new_state.define_errors)
        counts["preprocessing_errors"] = len(new_state.preprocessing_errors)
        logger.info("Référentiel rechargé (swap atomique): %s", counts)
        return counts

    def normalize(
        self, label: str, unit: Optional[str], value: Any, data_type: Optional[str] = "numeric"
    ) -> Dict[str, Any]:
        return self._state.normalize(label, unit, value, data_type)

    def normalize_range(
        self, label: str, unit: Optional[str], min_val: float, max_val: float
    ) -> Dict[str, Any]:
        return self._state.normalize_range(label, unit, min_val, max_val)

    def validate_proposed(
        self, proposed_payload: Dict[str, Any], label: str, unit: Optional[str], values: List[Any]
    ) -> Dict[str, Any]:
        """Gate 1 FIDÈLE : construit UN état jetable = référentiel courant + lignes proposées,
        puis exécute le VRAI pipeline `normalize` (preprocessing/rewrite/désambiguïsation inclus)
        pour CHAQUE valeur (min ET max d'une plage) — un seul build de registre pour toutes.

        Retourne {ok, valeur_canonique, unite_canonique} : ok=True ssi TOUTES les valeurs
        se normalisent. (Aucune valeur fournie -> ok=False.)"""
        with self._lock:
            merged = self._referentiel.merged_with(proposed_payload)
        temp_state = _NormalizerState(merged)  # construit une seule fois pour toutes les valeurs

        if not values:
            return {"ok": False}
        first: Dict[str, Any] = {}
        for value in values:
            result = temp_state.normalize(label, unit, value, "numeric")
            if not result:
                return {"ok": False}
            if not first:
                first = result
        return {
            "ok": True,
            "valeur_canonique": first.get("valeur_canonique"),
            "unite_canonique": first.get("unite_canonique"),
        }
