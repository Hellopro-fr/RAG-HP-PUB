import pytest

from app.core.execution import AgentIntrouvable, Dependances, executer_agent
from app.core.modeles import ErreurConfiguration
from tests.fakes import FauxApiV2, ModeleScripte, fiche_get_siren, reponse


def deps_avec(api, *reponses):
    modele = ModeleScripte(*reponses)
    return Dependances(api_v2=api, fabrique_modele=lambda definition, capacites: modele)


def test_execution_ok_journalisee():
    api = FauxApiV2()
    resultat = executer_agent("get-siren", "exemple.fr", "publiee", "identification_prospects", None,
                              deps_avec(api, reponse("12345678900012", 800, 12)))
    assert resultat["statut"] == "ok" and resultat["output"] == "12345678900012"
    assert resultat["execution_id"] == 42 and resultat["cout_usd"] == 0.0012
    assert resultat["agent"] == "get-siren" and resultat["version"] == 3
    journal = api.executions[0]
    assert journal["statut"] == 1 and journal["est_test"] == 0
    assert journal["id_agent"] == 1 and journal["id_version"] == 7
    assert journal["fournisseur"] == "gemini" and journal["modeles"] == "gemini-3.5-flash-lite"
    assert journal["tokens_entree"] == 800 and journal["origine"] == "identification_prospects"


def test_brouillon_journalise_comme_test():
    api = FauxApiV2()
    executer_agent("get-siren", "exemple.fr", "brouillon", "test_admin", 12,
                   deps_avec(api, reponse("Non trouvé")))
    assert api.lectures == [("get-siren", "brouillon")]
    assert api.executions[0]["est_test"] == 1 and api.executions[0]["id_user_bo"] == 12


def test_agent_introuvable_sans_appel_ni_journal():
    api = FauxApiV2(fiche={"trouve": False, "raison": "aucune_version_publiee"})
    modele = ModeleScripte()
    deps = Dependances(api_v2=api, fabrique_modele=lambda d, c: modele)
    with pytest.raises(AgentIntrouvable) as exc:
        executer_agent("get-siren", "exemple.fr", "publiee", "x", None, deps)
    assert exc.value.raison == "aucune_version_publiee"
    assert modele.recus == [] and api.executions == []


def test_configuration_incompatible_devient_erreur_journalisee():
    api = FauxApiV2()

    def fabrique(definition, capacites):
        raise ErreurConfiguration("MCP natif indisponible pour gemini/gemini-3.5-flash-lite")

    resultat = executer_agent("get-siren", "exemple.fr", "publiee", "x", None,
                              Dependances(api_v2=api, fabrique_modele=fabrique))
    assert resultat["statut"] == "erreur" and "MCP natif" in resultat["erreur"]
    assert api.executions[0]["statut"] == 3


def test_journal_perdu_la_reponse_part_quand_meme():
    api = FauxApiV2(journal={"id_execution": None, "cout": None})
    resultat = executer_agent("get-siren", "exemple.fr", "publiee", "x", None,
                              deps_avec(api, reponse("12345678900012")))
    assert resultat["output"] == "12345678900012"
    assert resultat["execution_id"] is None and resultat["cout_usd"] is None


def fiche_modifiee(**definition):
    fiche = fiche_get_siren()
    fiche["definition"] = {**fiche["definition"], **definition} if definition else fiche["definition"]
    return fiche


@pytest.mark.parametrize("fiche", [
    fiche_modifiee(relances=None),
    fiche_modifiee(format_sortie="regex"),
    {**fiche_get_siren(), "definition": []},
])
def test_fiche_mal_formee_erreur_journalisee_sans_appel(fiche):
    api = FauxApiV2(fiche=fiche)
    modele = ModeleScripte()
    resultat = executer_agent("get-siren", "exemple.fr", "publiee", "x", None,
                              Dependances(api_v2=api, fabrique_modele=lambda d, c: modele))
    assert resultat["statut"] == "erreur" and "fiche invalide" in resultat["erreur"]
    assert modele.recus == [] and api.executions[0]["statut"] == 3


def test_defaut_imprevu_dans_le_graphe_journalise_plutot_qu_un_500():
    # valeur de regex non textuelle : re.fullmatch lève TypeError dans le nœud valider
    api = FauxApiV2(fiche=fiche_modifiee(format_sortie={"type": "regex", "valeur": 5}))
    resultat = executer_agent("get-siren", "exemple.fr", "publiee", "x", None,
                              deps_avec(api, reponse("12345678900012")))
    assert resultat["statut"] == "erreur" and "TypeError" in resultat["erreur"]
    assert api.executions[0]["statut"] == 3


def test_variables_et_trace_journalisees_et_renvoyees():
    api = FauxApiV2(fiche=fiche_modifiee(instructions="SIRET de {{domaine}} ({{nom_domaine}}), pays {{pays}}.",
                                         variables={"pays": {"defaut": "FR"}}))
    message = reponse("12345678900012")
    message.response_metadata = {"trace": {"recherches": [{"requete": "hellopro siren"}], "tokens_outils": 0}}
    modele = ModeleScripte(message)
    deps = Dependances(api_v2=api, fabrique_modele=lambda d, c: modele)
    resultat = executer_agent("get-siren", "https://www.hellopro.fr/", "brouillon", "test_admin", 2256, deps,
                              variables={"pays": "BE"})
    assert modele.recus[0][0].content == "SIRET de hellopro.fr (hellopro), pays BE."
    trace = api.executions[0]["trace"]
    assert trace["recherches"] == [{"requete": "hellopro siren"}]
    assert trace["variables"] == {"domaine": "hellopro.fr", "nom_domaine": "hellopro", "pays": "BE"}
    assert resultat["trace"] == trace


def test_variable_sans_valeur_erreur_journalisee_sans_appel():
    api = FauxApiV2(fiche=fiche_modifiee(instructions="Pays {{pays}}", variables={"pays": {}}))
    modele = ModeleScripte()
    resultat = executer_agent("get-siren", "hellopro.fr", "publiee", "x", None,
                              Dependances(api_v2=api, fabrique_modele=lambda d, c: modele))
    assert resultat["statut"] == "erreur" and "{{pays}}" in resultat["erreur"]
    assert modele.recus == [] and api.executions[0]["statut"] == 3
