"""Graphe LangGraph de l'agent simple (doc de décision §4.1).

preparer → appeler_modele → valider → fin | corriger → appeler_modele | echec.
Les outils natifs sont exécutés par le fournisseur pendant appeler_modele.
"""
import json
import logging
from typing import Callable, List, TypedDict

import httpx
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph

from app.core.format_sortie import verifier_format
from app.core.usage import additionner_usage, extraire_usage

logger = logging.getLogger(__name__)

STATUT_OK, STATUT_FORMAT_INVALIDE, STATUT_ERREUR, STATUT_TIMEOUT = 1, 2, 3, 4
MAX_RELANCES = 0  # relance désactivée pour tous (décision du 01/10/2026) : format faux → echec


class EtatAgent(TypedDict, total=False):
    entree: str
    definition: dict
    messages: List[BaseMessage]
    sortie: str
    essais: int
    statut: int
    erreur: str
    message_format: str
    usage: dict
    etapes: List[str]


def _est_timeout(exc: Exception) -> bool:
    return isinstance(exc, (TimeoutError, httpx.TimeoutException)) or "timeout" in type(exc).__name__.lower()


def construire_graphe(fabrique_modele: Callable[[dict], object]):
    """fabrique_modele(definition) renvoie un objet dont .invoke(messages) renvoie un AIMessage."""

    def preparer(etat: EtatAgent) -> dict:
        instructions = (etat["definition"].get("instructions") or "").replace("{entree}", etat["entree"])
        return {"messages": [SystemMessage(instructions), HumanMessage(etat["entree"])], "essais": 0,
                "usage": {"tokens_entree": 0, "tokens_sortie": 0, "recherches": 0}, "etapes": ["preparer"]}

    def appeler_modele(etat: EtatAgent) -> dict:
        etapes = etat["etapes"] + ["appeler_modele"]
        try:
            reponse: AIMessage = fabrique_modele(etat["definition"]).invoke(etat["messages"])
        except Exception as exc:  # erreurs fournisseur, configuration, jeton MCP
            logger.warning("appel modèle en échec : %s", exc)
            statut = STATUT_TIMEOUT if _est_timeout(exc) else STATUT_ERREUR
            return {"statut": statut, "erreur": f"{type(exc).__name__}: {exc}", "etapes": etapes}

        # Réponse complète du fournisseur : texte, tokens, et recherches (grounding_metadata chez Gemini)
        reponse_complete = json.dumps(reponse.model_dump(), ensure_ascii=False, default=str)
        logger.info("réponse complète du modèle : %s", reponse_complete)

        texte = reponse.text.strip()
        # On renvoie seulement le texte au tour suivant : les blocs d'outils serveur ne se rejouent pas.
        return {"sortie": texte, "messages": etat["messages"] + [AIMessage(texte)], "essais": etat["essais"] + 1,
                "usage": additionner_usage(etat["usage"], extraire_usage(reponse)), "etapes": etapes}

    def valider(etat: EtatAgent) -> dict:
        ok, message = verifier_format(etat["sortie"], etat["definition"].get("format_sortie") or {})
        return {"statut": STATUT_OK if ok else 0, "message_format": message,
                "etapes": etat["etapes"] + ["valider"]}

    def corriger(etat: EtatAgent) -> dict:
        consigne = (f"Ta réponse ne respecte pas le format attendu : {etat['message_format']}. "
                    "Réponds uniquement dans ce format, sans aucun autre texte.")
        return {"messages": etat["messages"] + [HumanMessage(consigne)], "etapes": etat["etapes"] + ["corriger"]}

    def echec(etat: EtatAgent) -> dict:
        return {"statut": STATUT_FORMAT_INVALIDE, "erreur": etat["message_format"],
                "etapes": etat["etapes"] + ["echec"]}

    def apres_appel(etat: EtatAgent) -> str:
        return END if etat.get("statut") in (STATUT_ERREUR, STATUT_TIMEOUT) else "valider"

    def apres_validation(etat: EtatAgent) -> str:
        if etat["statut"] == STATUT_OK:
            return END
        relances = min(int(etat["definition"].get("relances", 1)), MAX_RELANCES)
        return "corriger" if etat["essais"] <= relances else "echec"

    graphe = StateGraph(EtatAgent)
    for nom, noeud in (("preparer", preparer), ("appeler_modele", appeler_modele), ("valider", valider),
                       ("corriger", corriger), ("echec", echec)):
        graphe.add_node(nom, noeud)
    graphe.add_edge(START, "preparer")
    graphe.add_edge("preparer", "appeler_modele")
    graphe.add_conditional_edges("appeler_modele", apres_appel, ["valider", END])
    graphe.add_conditional_edges("valider", apres_validation, [END, "corriger", "echec"])
    graphe.add_edge("corriger", "appeler_modele")
    graphe.add_edge("echec", END)
    return graphe.compile()
