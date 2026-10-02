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


def test_format_invalide_sans_relance_meme_si_la_fiche_en_demande():
    # Relance désactivée pour tous les fournisseurs : un seul appel, la sortie est gardée
    modele = ModeleScripte(reponse("Le SIRET est 12345678900012"))
    etat = lancer(modele, relances=2)
    assert etat["statut"] == STATUT_FORMAT_INVALIDE
    assert etat["sortie"] == "Le SIRET est 12345678900012"
    assert etat["essais"] == 1 and len(modele.recus) == 1
    assert etat["etapes"] == ["preparer", "appeler_modele", "valider", "echec"]
    assert "format" in etat["erreur"]


def test_erreur_du_fournisseur():
    etat = lancer(ModeleScripte(RuntimeError("401 invalid api key")))
    assert etat["statut"] == STATUT_ERREUR and "401" in etat["erreur"]
    assert "valider" not in etat["etapes"]


def test_delai_depasse():
    etat = lancer(ModeleScripte(httpx.ReadTimeout("lecture trop longue")))
    assert etat["statut"] == STATUT_TIMEOUT


def test_non_trouve_accentue_accepte():
    assert lancer(ModeleScripte(reponse("Non trouvé")))["statut"] == STATUT_OK


def test_reponse_complete_du_modele_dans_le_log(caplog):
    message = reponse("47893401100030")
    message.response_metadata = {"grounding_metadata": {"web_search_queries": ["sol-equestre.fr siret"]}}
    with caplog.at_level("INFO", logger="app.graphe.agent_simple"):
        lancer(ModeleScripte(message))
    assert "47893401100030" in caplog.text
    assert "sol-equestre.fr siret" in caplog.text  # métadonnées de recherche du fournisseur
    assert "input_tokens" in caplog.text
