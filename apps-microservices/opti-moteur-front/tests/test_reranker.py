"""Tests unitaires du reranker."""
from unittest import mock

from app.services import reranker
from app.services.reranker import rerank_candidates


def make_group(id_prod, nom, categorie, vec_dist=0.3, text_match=1000000):
    return {
        "hits": [{
            "document": {
                "id_produit": id_prod,
                "nom_produit": nom,
                "categorie": categorie,
            },
            "vector_distance": vec_dist,
            "text_match": text_match,
        }]
    }


class TestRerank:
    def test_empty(self):
        assert rerank_candidates([], "foo") == []

    def test_winner_has_best_vec_and_name_match(self):
        groups = [
            make_group("A", "Armoire médicale", "Armoire médicale", vec_dist=0.2, text_match=900000),
            make_group("B", "Chaise bureau",    "Mobilier",         vec_dist=0.5, text_match=100000),
        ]
        ranked = rerank_candidates(groups, "armoire medicale")
        assert ranked[0]["doc"]["id_produit"] == "A"
        assert ranked[0]["final_score"] > ranked[1]["final_score"]

    def test_noise_penalty_applied(self):
        # Item avec vec tres faible ET name_match faible -> penalty
        groups = [
            make_group("noise", "Chose sans rapport", "Autre categorie", vec_dist=0.9, text_match=1000000),
            make_group("good",  "Armoire médicale",  "Armoire médicale", vec_dist=0.2, text_match=500000),
        ]
        ranked = rerank_candidates(groups, "armoire medicale")
        # Le noise doit etre penalise (vec<0.20 AND name_match<0.50)
        noise_entry = next(r for r in ranked if r["doc"]["id_produit"] == "noise")
        assert noise_entry["penalty"] == "noise_bm25"
        # Good doit etre premier
        assert ranked[0]["doc"]["id_produit"] == "good"


class TestIdfWeightedMatch:
    """
    A4 (2026-05-18) : verifie que name_match privilegie les tokens rares quand
    l'IDF est disponible. Quand l'IDF n'est pas charge (test default), on tombe
    sur le ratio simple historique - backward-compat preservee.
    """

    def test_falls_back_to_simple_ratio_without_idf(self):
        # Pas de fichier IDF dans l'environnement de test -> ratio simple.
        # On verifie indirectement via le winner : "conique" matche les 2 docs,
        # mais le premier matche aussi "melangeur" -> ratio 2/2 vs 1/2.
        groups = [
            make_group("both",   "Melangeur conique 5L", "Melangeurs",  vec_dist=0.3, text_match=800000),
            make_group("partial", "Saleuse conique",     "Saleuses",    vec_dist=0.3, text_match=400000),
        ]
        ranked = rerank_candidates(groups, "melangeur conique")
        assert ranked[0]["doc"]["id_produit"] == "both"

    def test_idf_weighting_lifts_rare_token_match(self):
        """
        Quand l'IDF est disponible et que `conique` est plus rare que
        `melangeur`, un produit qui matche uniquement "conique" (mais pas
        "melangeur") doit avoir un name_match > 0.5 (au lieu de 0.5 strict
        avec le ratio simple).
        """
        # Mock le loader IDF pour ce test : "melangeur" tres frequent (idf bas),
        # "conique" rare (idf eleve).
        fake_idf = {"melangeur": 1.0, "conique": 4.0}

        with mock.patch.object(reranker, "idf_available", return_value=True), \
             mock.patch.object(reranker, "get_idf",
                               side_effect=lambda t: fake_idf.get(t, 2.0)):
            groups = [
                make_group("rare_only", "Saleuse conique", "Saleuses",
                           vec_dist=0.3, text_match=400000),
            ]
            ranked = rerank_candidates(groups, "melangeur conique")
            # name_match_idf = idf("conique") / (idf("conique") + idf("melangeur"))
            #                = 4.0 / (4.0 + 1.0) = 0.80  (vs 0.5 en ratio simple)
            assert ranked[0]["name_match"] == 0.8

    def test_idf_weighting_drops_common_token_match(self):
        """
        Inverse : un produit qui matche seulement "melangeur" (token commun)
        doit avoir un name_match < 0.5 (vs 0.5 strict avec le ratio simple).
        """
        fake_idf = {"melangeur": 1.0, "conique": 4.0}

        with mock.patch.object(reranker, "idf_available", return_value=True), \
             mock.patch.object(reranker, "get_idf",
                               side_effect=lambda t: fake_idf.get(t, 2.0)):
            groups = [
                make_group("common_only", "Melangeur classique", "Melangeurs",
                           vec_dist=0.3, text_match=400000),
            ]
            ranked = rerank_candidates(groups, "melangeur conique")
            # name_match_idf = 1.0 / 5.0 = 0.20
            assert abs(ranked[0]["name_match"] - 0.20) < 1e-9

    def test_idf_full_match_still_one(self):
        """Si tous les tokens query matchent, name_match doit toujours valoir 1.0."""
        fake_idf = {"melangeur": 1.0, "conique": 4.0}

        with mock.patch.object(reranker, "idf_available", return_value=True), \
             mock.patch.object(reranker, "get_idf",
                               side_effect=lambda t: fake_idf.get(t, 2.0)):
            groups = [
                make_group("full", "Melangeur conique 5L", "Melangeurs",
                           vec_dist=0.3, text_match=400000),
            ]
            ranked = rerank_candidates(groups, "melangeur conique")
            assert ranked[0]["name_match"] == 1.0
