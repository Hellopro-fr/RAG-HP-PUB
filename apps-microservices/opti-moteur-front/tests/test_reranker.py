"""Tests unitaires du reranker."""
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
