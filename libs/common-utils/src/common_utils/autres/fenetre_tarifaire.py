"""Fenêtres de facturation DeepSeek — heures pleines / heures creuses.

Les bornes sont fixées **en UTC** par le fournisseur
(https://api-docs.deepseek.com/quick_start/pricing). Depuis le 16-08-2026 16:00 UTC,
les heures pleines sont facturées le **double** des heures creuses :

    heures pleines : 01:00-04:00 et 06:00-10:00 UTC
    heures creuses : tout le reste (17 h sur 24), moitié prix

Comparaison en UTC, jamais en heure locale. Les bornes étant fixées en UTC, un test
écrit en Europe/Paris se décale d'une heure à chaque changement d'heure : mesuré, le
créneau « 22h-6h Paris » contient 3 heures pleines en été (3, 4, 5) et 3 **autres** en
hiver (2, 3, 4), sans qu'une seule ligne de code ne change. C'est le défaut que ce
module existe pour éviter.

Vit dans ``autres`` — un namespace package **sans ``__init__.py`` et sans dépendance
hors stdlib** — et non dans ``rabbitmq`` ou ``concurrency``, pour la même raison que
``autres/graceful.py`` : le ``__init__`` de ``concurrency`` importe le garde de
concurrence Milvus (``prometheus_client``/``redis``), que des services comme
nettoyage-bruit-ocr-service **n'installent pas**. Or ce module est importé **à l'import
du consumer** : un import en cascade tuerait le conteneur au démarrage, et
``restart: unless-stopped`` le relancerait en boucle.

Consommateurs au 20-08-2026 : QC-caracterisation (2 consumers), QC-fabricant-reference,
template-llm-service, nettoyage-bruit-ocr-service.

Limite connue : ``datetime.now(timezone.utc)`` lit l'horloge système du conteneur. Si
elle est fausse, la fenêtre est fausse. La garde ne perd aucun message dans ce cas —
elle suspend ou reprend au mauvais moment, ce qui est un coût, pas une panne. Avec
19 replicas au total, chacun lit sa propre horloge : une dérive sur un hôte fait
consommer au tarif double sans qu'aucun log ne le signale.
"""

import logging
import os
from datetime import datetime, timezone
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# (heure de début incluse, heure de fin exclue), en UTC — la grille DeepSeek.
FENETRES_PAR_DEFAUT = ((1, 4), (6, 10))

# Nom de la variable d'environnement qui peut surcharger la grille, au format
# "1-4,6-10". Deux usages : ajuster sans rebuild d'image si DeepSeek change ses
# horaires, et forcer une fenêtre courte pour tester la garde contre un vrai broker
# sans attendre 1 h du matin.
#
# ⚠️ Pour être lisible dans un conteneur, elle doit figurer dans le bloc
# ``environment:`` du service dans docker-compose.yml : ces services n'ont pas
# d'``env_file``.
VAR_ENV_FENETRES = "DEEPSEEK_FENETRES_PLEINES"


def parser_fenetres(brut: Optional[str]) -> Tuple[Tuple[int, int], ...]:
    """Analyse une grille au format "1-4,6-10". Retombe sur le défaut si invalide.

    Ne lève JAMAIS : une variable d'environnement mal écrite ne doit pas empêcher le
    service de démarrer. Elle est signalée dans les logs et ignorée.
    """
    if not brut or not brut.strip():
        return FENETRES_PAR_DEFAUT

    fenetres = []
    for morceau in brut.split(","):
        morceau = morceau.strip()
        if not morceau:
            continue
        try:
            debut_txt, fin_txt = morceau.split("-")
            debut, fin = int(debut_txt), int(fin_txt)
        except ValueError:
            logger.warning(
                "%s : segment '%s' illisible (attendu « debut-fin »), grille par "
                "défaut conservée", VAR_ENV_FENETRES, morceau
            )
            return FENETRES_PAR_DEFAUT
        if not (0 <= debut < fin <= 24):
            logger.warning(
                "%s : segment '%s' hors bornes (0 <= debut < fin <= 24), grille par "
                "défaut conservée", VAR_ENV_FENETRES, morceau
            )
            return FENETRES_PAR_DEFAUT
        fenetres.append((debut, fin))

    if not fenetres:
        return FENETRES_PAR_DEFAUT
    return tuple(fenetres)


# Résolue une seule fois au chargement : la grille ne change pas en cours de vie du
# processus, et la relire à chaque message serait un appel système par appel LLM.
FENETRES_PLEINES = parser_fenetres(os.environ.get(VAR_ENV_FENETRES))

if FENETRES_PLEINES != FENETRES_PAR_DEFAUT:
    logger.warning(
        "Grille tarifaire SURCHARGÉE par %s : %s (défaut : %s)",
        VAR_ENV_FENETRES, FENETRES_PLEINES, FENETRES_PAR_DEFAUT,
    )


def _heure_utc(maintenant: Optional[datetime] = None) -> int:
    if maintenant is None:
        maintenant = datetime.now(timezone.utc)
    return maintenant.astimezone(timezone.utc).hour


def est_heure_pleine(maintenant: Optional[datetime] = None) -> bool:
    """True si l'instant tombe dans une fenêtre facturée au tarif double.

    :param maintenant: instant à tester ; par défaut l'heure UTC courante.
        N'est passé que par les tests — le code de production ne le fournit jamais.
    """
    heure = _heure_utc(maintenant)
    return any(debut <= heure < fin for debut, fin in FENETRES_PLEINES)


def libelle_fenetre(maintenant: Optional[datetime] = None) -> str:
    """Libellé lisible de la fenêtre en cours, destiné aux logs."""
    heure = _heure_utc(maintenant)
    for debut, fin in FENETRES_PLEINES:
        if debut <= heure < fin:
            return f"heures pleines {debut:02d}:00-{fin:02d}:00 UTC (tarif double)"
    return "heures creuses (moitié prix)"
