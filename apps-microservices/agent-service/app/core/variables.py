"""Variables {{nom}} des instructions : fournies à l'appel, sinon valeur par défaut de la fiche, sinon calculées.

Double accolade pour ne pas toucher aux accolades d'exemples ou de JSON du prompt. {entree} reste remplacée.
"""
import re
from typing import Dict, Tuple
from urllib.parse import urlsplit

MOTIF = re.compile(r"\{\{\s*([a-z_][a-z0-9_]*)\s*\}\}")


class VariableManquante(Exception):
    pass


def variables_calculees(entree: str) -> Dict[str, str]:
    """entree telle quelle ; domaine sans schéma, www., port ni chemin ; nom_domaine sans extension."""
    brut = entree.strip()
    hote = urlsplit(brut if "://" in brut else "http://" + brut).hostname or brut
    domaine = hote.lower().removeprefix("www.")
    return {"entree": entree, "domaine": domaine, "nom_domaine": domaine.split(".")[0]}


def resoudre_variables(instructions: str, entree: str, declarees: dict,
                       fournies: Dict[str, str]) -> Tuple[str, Dict[str, str]]:
    """Renvoie (instructions remplacées, valeurs utilisées). VariableManquante si une variable n'a aucune valeur."""
    calculees = variables_calculees(entree)
    valeurs = {}

    def valeur(trouve) -> str:
        nom = trouve.group(1)
        if nom == "entree":
            resultat = entree
        elif nom in (fournies or {}):
            resultat = str(fournies[nom])
        elif "defaut" in ((declarees or {}).get(nom) or {}):
            resultat = str(declarees[nom]["defaut"])
        elif nom in calculees:
            resultat = calculees[nom]
        else:
            raise VariableManquante(f"variable {{{{{nom}}}}} sans valeur (ni fournie à l'appel, ni par défaut)")
        if nom != "entree":
            valeurs[nom] = resultat
        return resultat

    texte = MOTIF.sub(valeur, instructions).replace("{entree}", entree)
    return texte, valeurs
