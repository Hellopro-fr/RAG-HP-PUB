from app.core.variables import resoudre_variables

DECLAREES = {"nom": {"motif": "{nom}"}, "pays": {"motif": "{Pays du client}"}}


def test_variables_cochees_remplacees_par_les_valeurs_fournies():
    texte, valeurs = resoudre_variables(
        'Société {nom} ({nom}), pays {Pays du client}, format {domaine+extension}, json {"a": 1}',
        "hellopro.fr", DECLAREES, {"nom": "HelloPro", "pays": "FR"})
    assert texte == 'Société HelloPro (HelloPro), pays FR, format {domaine+extension}, json {"a": 1}'
    assert valeurs == {"nom": "HelloPro", "pays": "FR"}


def test_variable_non_fournie_laissee_telle_quelle():
    texte, valeurs = resoudre_variables("Société {nom}, pays {Pays du client}", "x", DECLAREES, {"nom": "HelloPro"})
    assert texte == "Société HelloPro, pays {Pays du client}"
    assert valeurs == {"nom": "HelloPro"}


def test_valeur_fournie_pour_un_texte_non_coche_ignoree():
    texte, valeurs = resoudre_variables("Société {nom}", "x", {}, {"nom": "HelloPro"})
    assert texte == "Société {nom}" and valeurs == {}


def test_entree_remplacee_et_valeur_jamais_reinterpretee():
    # {entree} : comportement d'origine ; une valeur qui contient un motif n'est pas remplacée à son tour
    texte, _ = resoudre_variables("{nom} / {entree}", "hellopro.fr", DECLAREES, {"nom": "{entree}"})
    assert texte == "{entree} / hellopro.fr"
