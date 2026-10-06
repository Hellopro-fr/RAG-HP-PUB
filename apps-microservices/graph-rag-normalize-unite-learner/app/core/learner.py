"""
Traitement d'UNE unité inconnue (appelé en batch par BatchRunner).

Nouveau modèle (déclenchement manuel, tout INACTIF par défaut) :
  - LLM DeepSeek (prompt BDD) -> proposition de règle.
  - GATE 1 FIDÈLE : validation via /admin/validate du service dynamique (vrai moteur,
    préprocessing/réécritures/désambiguïsation inclus). Min ET max pour les plages.
      * OK  -> lignes écrites en base mais INACTIVES (actif=0, statut_revue=1) ;
               statut apprentissage 'pending_activation' (activation manuelle requise).
      * NOK -> aucune ligne écrite ; statut 'erreur_verification' (vérification manuelle).
  - Erreur de traitement (LLM, /admin/validate injoignable, save) -> remontée comme
    erreur de service (le message DLQ est requeue, pas de statut terminal).

Pas de seuil de confiance, pas de reload auto, pas de requeue vers la retry queue :
l'activation d'une unité apprise est un geste humain.
"""
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from app.config import settings
from app.core import dynamic_client
from app.core.api_client import DeepSeek, HelloProAPIClient

logger = logging.getLogger(__name__)

# Statuts d'issue d'une unité
STATUS_PENDING = "pending_activation"     # Gate 1 OK, écrit inactif, attend activation humaine
STATUS_VERIF_ERROR = "erreur_verification"  # Gate 1 NOK, attend vérification humaine
STATUS_PROCESSING_ERROR = "processing_error"  # erreur LLM/validate/save -> erreur service, requeue
STATUS_SKIPPED = "skipped"                # déjà traité lors d'un run précédent (libellé rapport, non persisté)

_LEARNED_ORDER = 9000  # ordre/priorité des lignes apprises (après le seed)


class ProcessingError(Exception):
    """Erreur de traitement d'une unité (LLM, validation injoignable, save) -> erreur service."""


@dataclass
class UnitOutcome:
    unite: str
    status: str
    reason: str = ""
    proposal: Optional[Dict[str, Any]] = field(default=None)
    error_type: Optional[str] = None  # processing_error uniquement : 'contract'|'transient'|'processing'


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    return None


class Learner:
    """Traite une unité. Dépendances injectables pour les tests."""

    # Statuts apprentissage considérés comme déjà traités (on ne refait pas le LLM).
    # Inclut les statuts legacy (learned/needs_review/rejected) pour rester compatible.
    _TERMINAL_STATUSES = {STATUS_PENDING, STATUS_VERIF_ERROR, "learned", "needs_review", "rejected"}

    def __init__(
        self,
        api_client: Optional[HelloProAPIClient] = None,
        validate_fn: Callable = dynamic_client.validate,
        deepseek_factory: Callable[[], DeepSeek] = lambda: DeepSeek(max_retries=5),
    ):
        self.api = api_client or HelloProAPIClient()
        self.validate_fn = validate_fn
        self.deepseek_factory = deepseek_factory
        self._prompt: Optional[str] = None

    async def close(self):
        await self.api.close()

    async def load_prompt(self) -> Optional[str]:
        if self._prompt is None:
            cfg = await self.api.get_prompt(settings.PROMPT_LEARNER_ID)
            self._prompt = (cfg or {}).get("contenu_prompt")
        return self._prompt

    # ------------------------------------------------------------------ #
    # LLM
    # ------------------------------------------------------------------ #
    async def _call_llm(self, label: str, unite: str, value: Any, referentiel: Dict[str, Any]) -> Dict[str, Any]:
        prompt_template = await self.load_prompt()
        if not prompt_template:
            raise ProcessingError(f"prompt learner introuvable (id={settings.PROMPT_LEARNER_ID})")

        canonical_units = referentiel.get("canonical_units", {})
        prompt = (
            prompt_template
            .replace("{label}", str(label))
            .replace("{unite}", str(unite))
            .replace("{valeur}", str(value))
            .replace("{dimensions_existantes}", json.dumps(sorted(canonical_units), ensure_ascii=False))
            .replace("{unites_canoniques}", json.dumps(canonical_units, ensure_ascii=False))
        )

        import asyncio
        deepseek = self.deepseek_factory()
        result = await asyncio.to_thread(deepseek.chat, prompt)

        # Tracking LLM — y compris en cas d'erreur (#8 : ne plus laisser l'échec non tracé).
        is_error = "code" in result
        response_obj = result.get("response")
        usage = getattr(response_obj, "usage", None)
        await self.api.log_llm_usage(
            type_ia=2, model=deepseek.MODEL,
            input_token=getattr(usage, "prompt_tokens", 0) or 0,
            output_token=getattr(usage, "completion_tokens", 0) or 0,
            id_process=settings.ID_PROCESS, origine="normalize-unite-learner",
            etat=2 if is_error else 1,
            retour_erreur=str(result.get("error", "")) if is_error else "",
        )
        if is_error:
            raise ProcessingError(f"LLM error: {result.get('error')}")

        proposal = _extract_json((result.get("content") or "").strip())
        if not proposal or not str(proposal.get("dimension") or "").strip():
            raise ProcessingError("LLM sans proposition exploitable")
        return proposal

    # ------------------------------------------------------------------ #
    # Sections proposées (pour /admin/validate) et lignes de sauvegarde
    # ------------------------------------------------------------------ #
    def _build_sections(
        self, proposal: Dict[str, Any], unite_key: str, current_canonicals: Dict[str, str],
    ) -> Dict[str, List[dict]]:
        """Sections au format payload (definitions/unite_dimension/...) sans flags — pour validate.
        Tous les champs issus du LLM sont coercés en str : un champ malformé (liste/dict/nombre)
        devient une valeur invalide rejetée par Gate 1 (NOK), jamais un crash (anti message-poison)."""
        dimension = str(proposal.get("dimension") or "").strip()
        sections: Dict[str, List[dict]] = {
            "unite_dimension": [{"unite": unite_key, "dimension": dimension}],
        }
        if dimension not in current_canonicals:
            canonical = str(proposal.get("unite_canonique") or "").strip()
            if canonical:
                sections["dimension_canonique"] = [{"dimension": dimension, "unite_canonique": canonical}]
        if proposal.get("pint_define"):
            sections["definitions"] = [{"definition": str(proposal["pint_define"]).strip(), "ordre": _LEARNED_ORDER}]
        if proposal.get("reecriture"):
            sections["reecriture"] = [{"unite_source": unite_key, "kind": "rewrite",
                                       "value": str(proposal["reecriture"]).strip()}]
        if proposal.get("label_to_dimension"):
            sections["label_dimension"] = [
                {"label": str(proposal["label_to_dimension"]).strip().lower(),
                 "dimension": dimension, "priorite": _LEARNED_ORDER}
            ]
        return sections

    # section payload -> table SQL (pour referentiel/save)
    _SECTION_TO_TABLE = {
        "unite_dimension": "unite_dimension",
        "dimension_canonique": "dimension_canonique",
        "definitions": "unite_definition",
        "reecriture": "reecriture",
        "label_dimension": "label_dimension",
    }

    async def _save_inactive(self, sections: Dict[str, List[dict]], confiance: float) -> None:
        """Écrit les lignes apprises INACTIVES (actif=0, statut_revue=1) — activation manuelle requise.
        Save ATOMIQUE (#4) : toutes les tables en UN appel transactionnel → un échec n'écrit rien
        (pas de ligne orpheline ni de doublon au retry). Lève ProcessingError si l'écriture échoue."""
        flags = {"est_auto": 1, "confiance": confiance, "statut_revue": 1, "actif": 0, "origine": "learner"}
        tables = {
            self._SECTION_TO_TABLE[section]: [{**row, **flags} for row in rows]
            for section, rows in sections.items()
        }
        res = await self.api.referentiel_save_batch(tables)
        if res is None or res.get("erreur"):
            raise ProcessingError(f"échec save référentiel (atomique): {res}")

    # ------------------------------------------------------------------ #
    # Traitement d'une unité
    # ------------------------------------------------------------------ #
    async def process_unit(
        self, unite_key: str, label: str, values: List[Any], referentiel: Dict[str, Any],
    ) -> UnitOutcome:
        # Dédup inter-run : déjà traité (pending/verif/learned/rejected) -> on ne refait pas
        appr = await self.api.apprentissage_get(unite_key, label) or {}
        if appr.get("statut") in self._TERMINAL_STATUSES:
            return UnitOutcome(unite_key, STATUS_SKIPPED, f"déjà '{appr.get('statut')}'")

        # 1. LLM (lève ProcessingError -> erreur service)
        value_repr = values[0] if values else None
        proposal = await self._call_llm(label, unite_key, value_repr, referentiel)

        # 2. GATE 1 fidèle via le service dynamique — min ET max pour les plages (#7)
        sections = self._build_sections(proposal, unite_key, referentiel.get("canonical_units", {}))
        proposed_payload = {k: [dict(r) for r in v] for k, v in sections.items()}

        if not values:
            await self.api.apprentissage_upsert(
                unite_key, label, statut=STATUS_VERIF_ERROR,
                raison_rejet="aucune valeur à valider", payload_llm=proposal,
            )
            return UnitOutcome(unite_key, STATUS_VERIF_ERROR, "aucune valeur à valider", proposal)

        # Gate 1 : un seul appel pour TOUTES les valeurs (min ET max). Lève DynamicValidationError.
        res = await self.validate_fn(proposed_payload, label, unite_key, values)
        if not res or not res.get("ok"):
            await self.api.apprentissage_upsert(
                unite_key, label, statut=STATUS_VERIF_ERROR,
                raison_rejet=f"validation NOK (valeurs={values})", payload_llm=proposal,
            )
            return UnitOutcome(unite_key, STATUS_VERIF_ERROR, f"Gate 1 NOK (valeurs={values})", proposal)

        # 3. Gate 1 OK -> écrire INACTIF + statut 'pending_activation' (activation manuelle requise)
        await self._save_inactive(sections, float(proposal.get("confiance") or 0))
        # L'upsert du statut DOIT réussir : sinon les lignes référentiel sont écrites mais sans
        # trace d'apprentissage -> au run suivant la dédup échoue et on re-appelle le LLM (coût).
        # On remonte une erreur de traitement (requeue) plutôt qu'un faux 'pending'. (#5)
        appr_res = await self.api.apprentissage_upsert(
            unite_key, label, statut=STATUS_PENDING,
            confiance=float(proposal.get("confiance") or 0), payload_llm=proposal,
        )
        if not appr_res or (isinstance(appr_res, dict) and appr_res.get("erreur")):
            raise ProcessingError(
                f"save référentiel OK mais upsert apprentissage échoué pour '{unite_key}'"
            )
        return UnitOutcome(unite_key, STATUS_PENDING, "appris (inactif, activation manuelle requise)", proposal)
