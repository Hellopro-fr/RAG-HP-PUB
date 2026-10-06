"""
Chargement du référentiel de normalisation d'unités depuis le BO v2 (PHP).

Le référentiel remplace TOUTES les données par-unité hardcodées du service historique
(dictionnaires + alias pint + chaîne de réécritures/sanitisation if/elif) :

  - definitions        -> pint define() bruts (rejoués dans l'ordre)
  - unit_to_dimension  -> UNIT_TO_DIMENSION  (lookup exact, clé minuscule)
  - label_to_dimension -> LABEL_TO_DIMENSION (match sous-chaîne, ORDONNÉ par priorite)
  - canonical_units    -> CANONICAL_UNITS    (dimension -> unité canonique)
  - preprocessing      -> transforms universels ordonnés (NFKC, strip parens, ·→., ³→3, ²→2)
  - rewrites           -> réécritures exactes unité->expression pint, ou bypass->canonique

NB : la désambiguïsation contextuelle (nm / t/min / G) reste STATIQUE en code
(`unit_normalization_service._STATIC_DISAMBIGUATIONS`) — 3 cas seulement, dynamisation
en base injustifiée.

La source est injectable : prod = `fetch_referentiel_from_bo()` (httpx),
test = `Referentiel.from_payload(dict)` avec un payload fixture.

⚠ Les LISTES ORDONNÉES (`label_to_dimension`, `preprocessing`) ne doivent JAMAIS être
converties en structures non ordonnées : leur ordre porte la sémantique (spécifique
avant générique, dépendances de transformation).
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PreprocessingRule:
    """Transform universel appliqué à toute unité. type ∈ {nfkc, regex_sub, str_replace}.

    phase :
      - 'pre_snapshot'  : appliqué AVANT le snapshot `original_unit` (sert au lookup dimension)
      - 'post_snapshot' : appliqué APRÈS (sert à l'expression pint finale)
    """
    type: str
    phase: str
    pattern: Optional[str] = None
    remplacement: str = ""


@dataclass(frozen=True)
class RewriteRule:
    """Réécriture exacte d'une unité (clé minuscule).

    kind :
      - 'rewrite' : remplace l'unité par `value` (expression pint)
      - 'bypass'  : retourne directement {valeur, value} sans passer par pint (value = canonique)
    """
    kind: str
    value: str


@dataclass(frozen=True)
class Referentiel:
    """Référentiel immuable chargé en mémoire (swap atomique à chaque reload)."""

    definitions: List[str] = field(default_factory=list)
    unit_to_dimension: Dict[str, str] = field(default_factory=dict)
    label_to_dimension: List[Tuple[str, str]] = field(default_factory=list)
    canonical_units: Dict[str, str] = field(default_factory=dict)
    preprocessing: List[PreprocessingRule] = field(default_factory=list)
    rewrites: Dict[str, RewriteRule] = field(default_factory=dict)

    def counts(self) -> Dict[str, int]:
        return {
            "definitions": len(self.definitions),
            "unit_to_dimension": len(self.unit_to_dimension),
            "label_to_dimension": len(self.label_to_dimension),
            "canonical_units": len(self.canonical_units),
            "preprocessing": len(self.preprocessing),
            "rewrites": len(self.rewrites),
        }

    def validate(self) -> None:
        """Garde-fou anti-référentiel-vide : les structures cœur de résolution de
        dimension doivent être non vides. Sans elles, le service ne normalise plus rien.

        Sert à détecter un payload BO mal formé (mauvaise enveloppe / clés renommées) :
        `from_payload` ne lève jamais (tous les `.get()` ratent silencieusement et
        produisent un référentiel vide). On lève ICI pour que le fail-fast du démarrage
        et le `/admin/reload` rejettent un référentiel inexploitable au lieu de le charger.
        Lève `ValueError` en listant les sections manquantes.
        """
        manquantes = [
            nom
            for nom, taille in (
                ("unit_to_dimension", len(self.unit_to_dimension)),
                ("label_to_dimension", len(self.label_to_dimension)),
                ("canonical_units", len(self.canonical_units)),
            )
            if taille == 0
        ]
        if manquantes:
            raise ValueError(
                f"Référentiel inexploitable, sections cœur vides: {manquantes}. "
                f"PRÉ-REQUIS : charger le seed (sql/03_seed_referentiel.sql) en base AVANT de "
                f"démarrer le service, ou vérifier que BO normalisation/referentiel/get répond "
                f"avec les sections (payload mal formé ?). counts={self.counts()}"
            )

    @classmethod
    def from_payload(cls, payload: Dict[str, Any]) -> "Referentiel":
        """
        Construit le référentiel depuis le payload BO v2 (déjà filtré actif=1).
        Tri défensif côté Python (ne dépend pas du tri SQL).
        """
        definitions_rows = sorted(
            payload.get("definitions", []),
            key=lambda r: int(r.get("ordre", 0) or 0),
        )
        definitions = [
            str(r["definition"]).strip()
            for r in definitions_rows
            if str(r.get("definition", "")).strip()
        ]

        unit_to_dimension: Dict[str, str] = {}
        for r in payload.get("unite_dimension", []):
            unite = str(r.get("unite", "")).strip().lower()
            dimension = str(r.get("dimension", "")).strip()
            if unite and dimension:
                unit_to_dimension[unite] = dimension

        label_rows = sorted(
            payload.get("label_dimension", []),
            key=lambda r: int(r.get("priorite", 0) or 0),
        )
        label_to_dimension: List[Tuple[str, str]] = []
        for r in label_rows:
            label = str(r.get("label", "")).strip().lower()
            dimension = str(r.get("dimension", "")).strip()
            if label and dimension:
                label_to_dimension.append((label, dimension))

        canonical_units: Dict[str, str] = {}
        for r in payload.get("dimension_canonique", []):
            dimension = str(r.get("dimension", "")).strip()
            unite_canonique = str(r.get("unite_canonique", "")).strip()
            if dimension and unite_canonique:
                canonical_units[dimension] = unite_canonique

        preprocessing_rows = sorted(
            payload.get("preprocessing", []),
            key=lambda r: int(r.get("ordre", 0) or 0),
        )
        preprocessing = [
            PreprocessingRule(
                type=str(r.get("type", "")).strip(),
                phase=str(r.get("phase", "pre_snapshot")).strip(),
                pattern=r.get("pattern"),
                remplacement=str(r.get("remplacement", "") or ""),
            )
            for r in preprocessing_rows
            if r.get("type")
        ]

        rewrites: Dict[str, RewriteRule] = {}
        for r in payload.get("reecriture", []):
            source = str(r.get("unite_source", "")).strip().lower()
            kind = str(r.get("kind", "rewrite")).strip()
            value = str(r.get("value", "") or "")
            if source and value:
                rewrites[source] = RewriteRule(kind=kind, value=value)

        return cls(
            definitions=definitions,
            unit_to_dimension=unit_to_dimension,
            label_to_dimension=label_to_dimension,
            canonical_units=canonical_units,
            preprocessing=preprocessing,
            rewrites=rewrites,
        )

    def merged_with(self, proposed_payload: Dict[str, Any]) -> "Referentiel":
        """Retourne un nouveau référentiel = courant + lignes proposées (pour /admin/validate).
        Les lignes proposées (apprises) s'ajoutent après les existantes (ordre/priorite élevés)."""
        p = Referentiel.from_payload(proposed_payload)
        return Referentiel(
            definitions=self.definitions + p.definitions,
            unit_to_dimension={**self.unit_to_dimension, **p.unit_to_dimension},
            label_to_dimension=self.label_to_dimension + p.label_to_dimension,
            canonical_units={**self.canonical_units, **p.canonical_units},
            preprocessing=self.preprocessing + p.preprocessing,
            rewrites={**self.rewrites, **p.rewrites},
        )


async def fetch_referentiel_from_bo() -> Referentiel:
    """
    Récupère le référentiel via BO v2 (CRUD côté PHP).

    POST {BO_V2_URL} body {etape, field, action, data} + Bearer HP_TOKEN — convention
    routeur webhook BO (identique au learner). Réponse enveloppée {code, response}.
    Lève en cas d'échec (le caller décide : fail-fast au démarrage, log au refresh).
    """
    body = {"etape": "normalisation", "field": "referentiel", "action": "get", "data": {}}
    headers = {"Authorization": f"Bearer {settings.HP_TOKEN}", "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=settings.BO_V2_TIMEOUT_SECONDS) as client:
        response = await client.post(settings.BO_V2_URL, json=body, headers=headers)
        response.raise_for_status()
        envelope = response.json()

    # BO renvoie {code:200, response:{...}} ; tolère aussi un payload direct (fixtures de test).
    payload = envelope["response"] if isinstance(envelope, dict) and "response" in envelope else envelope

    if not isinstance(payload, dict):
        # ex. {code:200, response:null} -> évite un AttributeError opaque dans from_payload
        raise ValueError(f"Payload BO inattendu (type {type(payload).__name__}, pas un objet JSON)")

    referentiel = Referentiel.from_payload(payload)
    referentiel.validate()  # rejette un payload BO mal formé (référentiel vide) avant chargement
    logger.info("Référentiel chargé depuis BO v2: %s", referentiel.counts())
    return referentiel
