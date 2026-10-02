"""Exécution complète d'un agent : fiche (API v2) → graphe → journal (API v2) → réponse."""
import logging
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

from app.core.trace import trace_vide
from app.graphe.agent_simple import STATUT_ERREUR, construire_graphe

logger = logging.getLogger(__name__)

NOMS_STATUT = {1: "ok", 2: "format_invalide", 3: "erreur", 4: "timeout"}


class AgentIntrouvable(Exception):
    def __init__(self, raison: str):
        super().__init__(raison)
        self.raison = raison


@dataclass
class Dependances:
    api_v2: Any                                        # ClientApiV2 ou double de test
    fabrique_modele: Callable[[dict, dict], object]    # (definition, capacites) -> modèle


def _probleme_definition(definition) -> Optional[str]:
    """Forme minimale d'une fiche (la validation complète est faite par l'admin, P3) ; None si correcte."""
    if not isinstance(definition, dict):
        return "la définition n'est pas un objet JSON"
    if not isinstance(definition.get("modele"), dict):
        return "« modele » absent ou invalide"
    for champ in ("format_sortie", "outils", "variables"):
        if not isinstance(definition.get(champ, {}), dict):
            return f"« {champ} » doit être un objet"
    relances = definition.get("relances", 1)
    if isinstance(relances, bool) or not isinstance(relances, int) or relances < 0:
        return "« relances » doit être un entier positif"
    return None


def executer_agent(code: str, entree: str, version: str, origine: str,
                   id_user_bo: Optional[int], deps: Dependances, variables: Optional[dict] = None) -> dict:
    """Lève AgentIntrouvable si la fiche est absente ; sinon journalise toujours l'exécution, jamais de 500."""
    fiche = deps.api_v2.lire_fiche(code, version) or {}
    if not fiche.get("trouve"):
        raise AgentIntrouvable(fiche.get("raison", "agent_inconnu"))
    definition, capacites = fiche.get("definition"), fiche.get("capacites") or {}
    probleme = _probleme_definition(definition)
    modele = {} if probleme else definition["modele"]

    debut = time.monotonic()
    if probleme:
        etat = {"statut": STATUT_ERREUR, "erreur": f"fiche invalide : {probleme}", "etapes": []}
    else:
        try:
            graphe = construire_graphe(lambda d: deps.fabrique_modele(d, capacites))
            etat = graphe.invoke({"entree": entree, "definition": definition, "variables": variables or {}})
        except Exception as exc:  # défaut imprévu d'un nœud : journalisé et renvoyé en erreur, pas en 500
            logger.exception("exécution de %s en échec", code)
            etat = {"statut": STATUT_ERREUR, "erreur": f"{type(exc).__name__}: {exc}", "etapes": []}
    duree_ms = int((time.monotonic() - debut) * 1000)
    usage = etat.get("usage") or {"tokens_entree": 0, "tokens_sortie": 0, "recherches": 0}
    trace = etat.get("trace") or trace_vide()

    journal = deps.api_v2.enregistrer_execution({
        "id_agent": fiche["id_agent"], "id_version": fiche["id_version"], "origine": origine,
        "est_test": 1 if version == "brouillon" else 0, "id_user_bo": id_user_bo,
        "entree": entree, "sortie": etat.get("sortie"), "statut": etat["statut"], "erreur": etat.get("erreur"),
        "etapes": etat.get("etapes", []), "fournisseur": modele.get("fournisseur", ""),
        "modeles": modele.get("nom", ""), "tokens_entree": usage["tokens_entree"],
        "tokens_sortie": usage["tokens_sortie"], "nb_recherches": usage["recherches"], "duree_ms": duree_ms,
        "trace": trace,
    })
    return {"output": etat.get("sortie"), "statut": NOMS_STATUT[etat["statut"]], "erreur": etat.get("erreur"),
            "agent": fiche["code"], "version": fiche["numero"], "etapes": etat.get("etapes", []),
            "usage": usage, "trace": trace, "cout_usd": journal["cout"], "duree_ms": duree_ms,
            "execution_id": journal["id_execution"]}
