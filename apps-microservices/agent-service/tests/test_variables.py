import pytest

from app.core.variables import VariableManquante, resoudre_variables, variables_calculees


def test_variables_calculees_depuis_l_entree():
    assert variables_calculees("https://www.Sol-Equestre.fr/mentions-legales?x=1") == {
        "entree": "https://www.Sol-Equestre.fr/mentions-legales?x=1",
        "domaine": "sol-equestre.fr", "nom_domaine": "sol-equestre"}
    assert variables_calculees("dechargement.com")["domaine"] == "dechargement.com"
    assert variables_calculees("dechargement.com")["nom_domaine"] == "dechargement"


def test_remplacement_fournie_puis_defaut_puis_calculee():
    texte, valeurs = resoudre_variables(
        "Domaine {{domaine}} ({{ nom_domaine }}), pays {{pays}}, langue {{langue}}, ancien {entree}, json {\"a\": 1}",
        "https://www.hellopro.fr/",
        declarees={"pays": {"defaut": "FR"}, "langue": {"defaut": "fr"}},
        fournies={"langue": "en"})
    assert texte == ('Domaine hellopro.fr (hellopro), pays FR, langue en, ancien https://www.hellopro.fr/, '
                     'json {"a": 1}')
    assert valeurs == {"domaine": "hellopro.fr", "nom_domaine": "hellopro", "pays": "FR", "langue": "en"}


def test_variable_obligatoire_non_fournie():
    with pytest.raises(VariableManquante, match=r"\{\{pays\}\}"):
        resoudre_variables("Pays {{pays}}", "hellopro.fr", declarees={"pays": {}}, fournies={})


def test_l_entree_ne_peut_pas_etre_remplacee_par_une_variable_fournie():
    texte, _ = resoudre_variables("{{entree}}", "hellopro.fr", declarees={}, fournies={"entree": "autre"})
    assert texte == "hellopro.fr"
