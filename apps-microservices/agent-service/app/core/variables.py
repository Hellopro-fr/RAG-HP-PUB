"""Variables des instructions : textes {…} cochés dans le BO, fiche « variables » = {"nom": {"motif": "{…}"}}.

Chaque motif est remplacé par la valeur « nom » passée à l'appel, laissé tel quel sinon.
{entree} reste remplacée par l'entrée de l'appel (comportement d'origine).
"""
import re
from typing import Dict, Tuple


def resoudre_variables(instructions: str, entree: str, declarees: dict,
                       fournies: Dict[str, str]) -> Tuple[str, Dict[str, str]]:
    """Renvoie (instructions remplacées, valeurs utilisées par nom)."""
    remplacements, valeurs = {}, {}
    for nom, options in (declarees or {}).items():
        motif = (options or {}).get("motif")
        if motif and nom in (fournies or {}):
            remplacements[motif] = valeurs[nom] = str(fournies[nom])
    remplacements.setdefault("{entree}", entree)

    # Un seul passage : une valeur qui contient un motif n'est pas remplacée à son tour
    motifs = re.compile("|".join(re.escape(m) for m in sorted(remplacements, key=len, reverse=True)))
    return motifs.sub(lambda trouve: remplacements[trouve.group(0)], instructions), valeurs
