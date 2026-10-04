"""Vérification du format de sortie d'un agent (champ format_sortie de la fiche)."""
import json
import re
from typing import Tuple


def verifier_format(sortie: str, format_sortie: dict) -> Tuple[bool, str]:
    """Renvoie (ok, message d'erreur). La sortie est comparée sans espaces autour.

    texte : tout sauf vide ; regex : correspondance complète ; json : objet ou liste seuls.
    """
    type_format = (format_sortie or {}).get("type", "texte")
    texte = (sortie or "").strip()
    if type_format == "texte":
        return (True, "") if texte else (False, "la réponse est vide")
    if type_format == "regex":
        motif = format_sortie.get("valeur", "")
        try:
            ok = re.fullmatch(motif, texte) is not None
        except re.error as exc:
            return False, f"expression régulière invalide dans la fiche : {exc}"
        return (True, "") if ok else (False, f"la réponse doit respecter le format {motif}")
    if type_format == "json":
        try:
            valeur = json.loads(texte)
        except ValueError:
            return False, "la réponse doit être un JSON valide, sans texte autour"
        if isinstance(valeur, (dict, list)):
            return True, ""
        return False, "la réponse doit être un objet ou une liste JSON"
    return False, f"type de format inconnu : {type_format}"
