from app.core.format_sortie import verifier_format

SIREN = {"type": "regex", "valeur": r"^(\d{14}|\d{9}|Non trouvé)$"}


def test_siret_accepte():
    assert verifier_format("12345678900012", SIREN) == (True, "")


def test_siren_avec_espaces_autour_accepte():
    assert verifier_format("  123456789 \n", SIREN)[0] is True


def test_non_trouve_avec_accent_accepte():
    assert verifier_format("Non trouvé", SIREN)[0] is True


def test_texte_autour_refuse():
    ok, message = verifier_format("Le SIRET est 12345678900012", SIREN)
    assert ok is False and "format" in message


def test_siret_avec_espaces_internes_refuse():
    assert verifier_format("123 456 789 00012", SIREN)[0] is False


def test_texte_vide_refuse():
    assert verifier_format("   ", {"type": "texte"}) == (False, "la réponse est vide")


def test_json_objet_accepte_et_texte_autour_refuse():
    assert verifier_format('{"statut": "actif"}', {"type": "json"})[0] is True
    assert verifier_format('Voici : {"statut": "actif"}', {"type": "json"})[0] is False


def test_regex_invalide_de_la_fiche_signalee():
    ok, message = verifier_format("abc", {"type": "regex", "valeur": "("})
    assert ok is False and "invalide" in message


def test_type_inconnu_refuse():
    assert verifier_format("abc", {"type": "xml"})[0] is False
