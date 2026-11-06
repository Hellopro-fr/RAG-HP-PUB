"""A511 : clean_json_response ne doit plus casser un pouce échappé en fin de titre.

Le modèle rend un JSON valide dont le titre finit par un pouce : ...1/2\"" puis }.
L'ancienne réparation (resp.replace('""', '"')) fusionnait le pouce échappé et le guillemet
fermant : ...1/2\"} -> « Tentative de parsing échouée », fiche sans produit, re-payée chaque nuit.
Données : tests/fixtures/a511_reponses_runs_739_740.json (runs 739 et 740, sans appel LLM).
"""
import json
import re
from pathlib import Path

import pytest

from app.core.optimize.traitement_donnees import TraitementDonnees

CAS = json.loads(
    (Path(__file__).parent / "fixtures" / "a511_reponses_runs_739_740.json").read_text(encoding="utf-8")
)
traitement = TraitementDonnees()


def lire(reponse_modele):
    """Chemin d'optimize.py : clean_json_response puis json.loads."""
    return json.loads(traitement.clean_json_response(reponse_modele))


def ancienne_reparation(resp):
    """fix_json_quotes avant A511 (prod f444e3901), pour prouver que les données couvrent le bogue."""
    resp = resp.replace('""', '"')
    return re.sub(r'(\d)"(\d)', r'\1\"\2', resp)


def test_reponse_brute_reelle_13951():
    titre = lire(CAS["reponse_brute_13951"])["Titre"]
    assert titre == 'Poignée de douchette MONOLITH Premium lg 225 - noir, raccord 1/2"'


@pytest.mark.parametrize("cas", CAS["echecs"], ids=lambda c: f'run{c["run"]}-{c["id"]}')
def test_echecs_des_runs_739_740_se_lisent(cas):
    assert lire(cas["modele"])["Titre"].endswith('"')


@pytest.mark.parametrize("cas", CAS["echecs"], ids=lambda c: f'run{c["run"]}-{c["id"]}')
def test_ancienne_reparation_reproduit_l_echec(cas):
    lu = ancienne_reparation(cas["modele"])
    assert lu == cas["lu"]
    with pytest.raises(json.JSONDecodeError):
        json.loads(lu)


@pytest.mark.parametrize("cas", CAS["succes_avec_pouce"], ids=lambda c: f'run{c["run"]}-{c["id"]}')
def test_succes_avec_pouce_inchanges(cas):
    reponse = json.dumps({"Titre": cas["titre"]}, ensure_ascii=False)
    assert lire(reponse) == {"Titre": cas["titre"]}


def test_pouce_au_milieu_inchange():
    assert lire('{"Titre": "Raccord 1/2\\" laiton - filetage mâle"}')["Titre"] == 'Raccord 1/2" laiton - filetage mâle'


def test_guillemets_doubles_hors_antislash_toujours_repares():
    assert lire('{""Titre"": ""Chaise de bureau ergonomique""}') == {"Titre": "Chaise de bureau ergonomique"}


def test_pouce_non_echappe_entre_chiffres_toujours_repare():
    assert lire('{"Titre": "Raccord 1"1/2 laiton"}')["Titre"] == 'Raccord 1"1/2 laiton'


def test_titre_vide_reste_en_echec():
    # Option b : comportement inchangé pour une réponse vide (pas de nom de produit vide en succès).
    with pytest.raises(json.JSONDecodeError):
        lire('{"Titre": ""}')
