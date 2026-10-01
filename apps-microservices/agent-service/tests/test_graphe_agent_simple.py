import httpx

from app.graphe.agent_simple import (STATUT_ERREUR, STATUT_FORMAT_INVALIDE, STATUT_OK, STATUT_TIMEOUT,
                                     construire_graphe)
from tests.fakes import ModeleScripte, definition_get_siren, reponse


def lancer(modele, relances=1, entree="exemple.fr"):
    graphe = construire_graphe(lambda definition: modele)
    return graphe.invoke({"entree": entree, "definition": definition_get_siren(relances)})


def test_reponse_correcte_du_premier_coup():
    modele = ModeleScripte(reponse("12345678900012", 800, 12))
    etat = lancer(modele)
    assert etat["statut"] == STATUT_OK and etat["sortie"] == "12345678900012"
    assert etat["essais"] == 1
    assert etat["etapes"] == ["preparer", "appeler_modele", "valider"]
    assert etat["usage"] == {"tokens_entree": 800, "tokens_sortie": 12, "recherches": 0}
    assert "exemple.fr" in modele.recus[0][0].content  # {entree} remplacé dans les instructions


def test_texte_autour_du_siret_corrige_par_une_relance():
    modele = ModeleScripte(reponse("Le SIRET est 12345678900012"), reponse("12345678900012"))
    etat = lancer(modele)
    assert etat["statut"] == STATUT_OK and etat["essais"] == 2
    assert "corriger" in etat["etapes"]
    assert "format attendu" in modele.recus[1][-1].content
    assert etat["usage"]["tokens_entree"] == 200


def test_format_toujours_faux_apres_relance_garde_la_derniere_sortie():
    modele = ModeleScripte(reponse("Le SIRET est 1"), reponse("Toujours pas"))
    etat = lancer(modele, relances=1)
    assert etat["statut"] == STATUT_FORMAT_INVALIDE
    assert etat["sortie"] == "Toujours pas"
    assert "format" in etat["erreur"] and etat["etapes"][-1] == "echec"


def test_erreur_du_fournisseur():
    etat = lancer(ModeleScripte(RuntimeError("401 invalid api key")))
    assert etat["statut"] == STATUT_ERREUR and "401" in etat["erreur"]
    assert "valider" not in etat["etapes"]


def test_delai_depasse():
    etat = lancer(ModeleScripte(httpx.ReadTimeout("lecture trop longue")))
    assert etat["statut"] == STATUT_TIMEOUT


def test_non_trouve_accentue_accepte():
    assert lancer(ModeleScripte(reponse("Non trouvé")))["statut"] == STATUT_OK
