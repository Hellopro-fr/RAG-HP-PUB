"""Doubles de test partagés (modèle scripté, API v2 en mémoire)."""
from langchain_core.messages import AIMessage


def definition_get_siren(relances=1):
    return {
        "modele": {"fournisseur": "gemini", "nom": "gemini-3.5-flash-lite", "temperature": 0},
        "instructions": "Trouve le SIRET du site {entree}.",
        "outils": {"recherche_web": {"max": 5}},
        "format_sortie": {"type": "regex", "valeur": r"^(\d{14}|\d{9}|Non trouvé)$"},
        "relances": relances,
    }


def fiche_get_siren(relances=1):
    return {"trouve": True, "id_agent": 1, "code": "get-siren", "type": 1, "id_version": 7, "numero": 3,
            "statut": 2, "definition": definition_get_siren(relances),
            "capacites": {"recherche_web": 1, "mcp": 0}}


def reponse(texte, entree=100, sortie=5):
    return AIMessage(content=texte, usage_metadata={"input_tokens": entree, "output_tokens": sortie,
                                                    "total_tokens": entree + sortie})


class ModeleScripte:
    """Renvoie les réponses (ou lève les exceptions) dans l'ordre ; garde les messages reçus."""

    def __init__(self, *reponses):
        self.reponses = list(reponses)
        self.recus = []

    def invoke(self, messages):
        self.recus.append(list(messages))
        suivante = self.reponses.pop(0)
        if isinstance(suivante, Exception):
            raise suivante
        return suivante


class FauxApiV2:
    def __init__(self, fiche=None, journal=None, erreur_lecture=None):
        self.fiche = fiche if fiche is not None else fiche_get_siren()
        self.journal_retour = journal or {"id_execution": 42, "cout": 0.0012}
        self.erreur_lecture = erreur_lecture
        self.lectures, self.executions = [], []

    def lire_fiche(self, code, version="publiee"):
        self.lectures.append((code, version))
        if self.erreur_lecture:
            raise self.erreur_lecture
        return self.fiche

    def enregistrer_execution(self, execution):
        self.executions.append(execution)
        return self.journal_retour
