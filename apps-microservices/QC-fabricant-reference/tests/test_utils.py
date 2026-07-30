"""Tests des utilitaires : extraction JSON tolerante aux sorties LLM."""
from app.core import utils


class TestExtractJsonFromText:
    def test_tableau_json_nu(self):
        assert utils.extract_json_from_text('[{"id_produit":"1","marque":"NOVARA"}]') == [
            {"id_produit": "1", "marque": "NOVARA"}
        ]

    def test_fences_markdown(self):
        texte = '```json\n[{"id_produit":"1","marque":null}]\n```'
        assert utils.extract_json_from_text(texte) == [{"id_produit": "1", "marque": None}]

    def test_texte_parasite_avant_et_apres(self):
        texte = 'Voici le resultat :\n[{"id_produit":"1"}]\nJ\'espere que cela convient.'
        assert utils.extract_json_from_text(texte) == [{"id_produit": "1"}]

    def test_tableau_vide(self):
        assert utils.extract_json_from_text("[]") == []

    def test_guillemets_typographiques(self):
        texte = '[{“id_produit”:”1”,”marque”:”NOVARA”}]'
        assert utils.extract_json_from_text(texte) == [{"id_produit": "1", "marque": "NOVARA"}]

    def test_texte_vide_retourne_none(self):
        assert utils.extract_json_from_text("") is None
        assert utils.extract_json_from_text("aucun json ici") is None

    def test_marque_avec_accents_preservee(self):
        """Le nettoyage hors-chaine ne doit pas amputer l'UTF-8 legitime."""
        resultat = utils.extract_json_from_text('[{"marque":"Précision Été"}]')
        assert resultat == [{"marque": "Précision Été"}]

    def test_caracteres_de_substitution_conserves(self):
        """Les titres corrompus (mojibake) ne doivent pas faire echouer le parsing."""
        resultat = utils.extract_json_from_text('[{"extrait_marque":"Pont \\u00e9l?vateur NOVARA"}]')
        assert resultat[0]["extrait_marque"].endswith("NOVARA")


class TestToJsonString:
    def test_accents_non_echappes(self):
        assert "é" in utils.to_json_string({"a": "é"})

    def test_objet_non_serialisable_ne_leve_pas(self):
        assert utils.to_json_string({"a": object()}) == "{}"
