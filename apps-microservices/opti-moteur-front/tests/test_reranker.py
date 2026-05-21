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
        # Apres A7 R3, le penalty contient aussi "low_coverage_50" car
        # aucun token query n'est dans le doc -> on verifie l'inclusion.
        noise_entry = next(r for r in ranked if r["doc"]["id_produit"] == "noise")
        assert "noise_bm25" in noise_entry["penalty"]
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


class TestSynonymsInReranker:
    """
    A6 (2026-05-20) : verifie que le reranker considere les synonymes Typesense
    pour le matching name/cat. Resout le cas multilingue "crane" -> "Grue XCMG".
    """

    def test_synonyms_match_lifts_grue_for_crane_query(self):
        """
        Query "crane" + doc "Grue XCMG" : sans synonymes, name_match=0.
        Avec synonymes {crane,grue,grues}, name_match=1.0 (le token query
        "crane" est couvert par "grue" present dans le nom).
        """
        syn_map = {
            "crane":   {"crane", "grue", "grues", "grutier"},
            "grue":    {"crane", "grue", "grues", "grutier"},
            "grues":   {"crane", "grue", "grues", "grutier"},
            "grutier": {"crane", "grue", "grues", "grutier"},
        }
        with mock.patch.object(reranker, "get_synonyms_map", return_value=syn_map):
            groups = [
                make_group("grue_xcmg", "Grue automotrice XCMG QY50KA - 50 tonnes", "Grues automotrices",
                           vec_dist=0.3, text_match=400000),
            ]
            ranked = rerank_candidates(groups, "crane")
            # "crane" est couvert via le synonyme "grue" -> name_match doit valoir 1.0
            assert ranked[0]["name_match"] == 1.0

    def test_no_synonyms_keeps_strict_matching(self):
        """
        Si syn_map vide (Typesense KO), le matching reste strict.
        Doc "Grue XCMG" ne matche PAS la query "crane" -> name_match=0.
        """
        with mock.patch.object(reranker, "get_synonyms_map", return_value={}):
            groups = [
                make_group("grue_xcmg", "Grue automotrice XCMG QY50KA", "Grues",
                           vec_dist=0.3, text_match=400000),
            ]
            ranked = rerank_candidates(groups, "crane")
            # Pas de synonyme -> matching strict -> name_match = 0
            assert ranked[0]["name_match"] == 0.0

    def test_synonyms_with_idf_keeps_idf_weighting(self):
        """
        Avec synonymes + IDF : le denominateur reste base sur les tokens query
        originaux (pas etendus), donc le score IDF n'est pas dilue.

        Query "soudure ritmo" :
          - syn cluster soudure : ["soudure","welding"]
          - syn cluster ritmo : (pas de synonyme, marque exacte)
        Doc "Soudeuse Ritmo" : matche les 2 tokens (soudure via stem, ritmo direct).
        """
        syn_map = {
            "soudure":  {"soudure", "soudures", "welding"},
            "soudures": {"soudure", "soudures", "welding"},
            "welding":  {"soudure", "soudures", "welding"},
        }
        # IDF fictif : ritmo est rare, soudure commune
        fake_idf = {"soudure": 1.5, "ritmo": 6.0, "welding": 6.0}

        with mock.patch.object(reranker, "get_synonyms_map", return_value=syn_map), \
             mock.patch.object(reranker, "idf_available", return_value=True), \
             mock.patch.object(reranker, "get_idf",
                               side_effect=lambda t: fake_idf.get(t, 2.0)):
            groups = [
                # Doc qui matche les 2 tokens directement (ritmo + soudure)
                make_group("apreau", "Machine pour soudure bout a bout Ritmo BASIC 250",
                           "Machines de soudure", vec_dist=0.3, text_match=900000),
                # Doc qui matche seulement "soudure" (un mot, pas ritmo)
                make_group("romus", "Chalumeau electronique Leister - soudure du cordon",
                           "Soudure", vec_dist=0.3, text_match=400000),
            ]
            ranked = rerank_candidates(groups, "soudure ritmo")
            # Apreau (les 2 tokens) doit etre premier
            assert ranked[0]["doc"]["id_produit"] == "apreau"
            assert ranked[0]["name_match"] == 1.0
            # Romus (1 token seulement) : name_match = idf(soudure) / (idf(soudure)+idf(ritmo))
            #                            = 1.5 / 7.5 = 0.20
            romus_entry = next(r for r in ranked if r["doc"]["id_produit"] == "romus")
            assert abs(romus_entry["name_match"] - 0.20) < 1e-9

    def test_synonyms_match_via_categorie(self):
        """
        Un token query est aussi couvert si son synonyme apparait dans
        `categorie` (pas seulement `nom_produit`).
        """
        syn_map = {
            "crane": {"crane", "grue", "grues"},
            "grue":  {"crane", "grue", "grues"},
            "grues": {"crane", "grue", "grues"},
        }
        with mock.patch.object(reranker, "get_synonyms_map", return_value=syn_map):
            groups = [
                # Le nom n'a pas "crane" ni "grue", mais la categorie oui
                make_group("xcmg", "XCMG QY50KA 50 tonnes", "Grues automotrices",
                           vec_dist=0.3, text_match=400000),
            ]
            ranked = rerank_candidates(groups, "crane")
            # name_match = 0 (nom_produit ne contient ni crane ni grue ni grues)
            # cat_match = 1.0 (categorie contient "grues" qui est synonyme de "crane")
            assert ranked[0]["cat_match"] == 1.0


class TestR3CoverageStrict:
    """
    A7 R3 (2026-05-21) : penalite coverage stricte si la majorite des tokens
    query ne sont pas couverts (ni en direct ni via synonymes).
    """

    def test_full_coverage_no_penalty(self):
        """Tous les tokens query couverts -> pas de penalite R3."""
        groups = [
            make_group("good", "Armoire medicale Optimea", "Armoires medicales",
                       vec_dist=0.3, text_match=900000),
        ]
        ranked = rerank_candidates(groups, "armoire medicale")
        # coverage = 2/2 = 1.0 -> pas de "low_coverage_*"
        assert "low_coverage" not in ranked[0]["penalty"]
        assert ranked[0]["coverage_ratio"] == 1.0

    def test_partial_coverage_70_percent_weak_penalty(self):
        """3 tokens query, 2 couverts (67%) -> weak penalty (* 0.75)."""
        groups = [
            # Query "barre laser led" : doc OPTICON matche "barre" + "laser" mais pas "led"
            make_group("opticon", "OPTICON Lecteur code barre laser OPL 6845R", "Lecteurs codes-barres",
                       vec_dist=0.3, text_match=800000),
        ]
        ranked = rerank_candidates(groups, "barre laser led")
        # coverage = 2/3 = 0.67 (entre 0.5 et 0.7) -> weak penalty
        assert ranked[0]["coverage_ratio"] < 0.70
        assert ranked[0]["coverage_ratio"] >= 0.50
        assert "low_coverage_70" in ranked[0]["penalty"]

    def test_low_coverage_strong_penalty(self):
        """3 tokens query, 1 couvert (33%) -> strong penalty (* 0.5)."""
        groups = [
            # Query "barre laser led" : doc "Veilleuse LED bureau" matche que "led"
            make_group("led_only", "Veilleuse LED de bureau elegante", "Lampes",
                       vec_dist=0.3, text_match=400000),
        ]
        ranked = rerank_candidates(groups, "barre laser led")
        # coverage = 1/3 = 0.33 (< 0.5) -> strong penalty
        assert ranked[0]["coverage_ratio"] < 0.50
        assert "low_coverage_50" in ranked[0]["penalty"]

    def test_full_match_outranks_partial(self):
        """Avec R3, un produit qui matche TOUS les tokens passe devant ceux qui en ratent."""
        groups = [
            # 3 tokens couverts (barre + laser + led present dans le nom)
            make_group("full", "Barre LED laser pour eclairage scenique", "Eclairage",
                       vec_dist=0.3, text_match=500000),
            # Seulement 2 tokens couverts (barre + laser, pas led)
            make_group("partial", "OPTICON Lecteur code barre laser OPL 6845R", "Lecteurs codes-barres",
                       vec_dist=0.3, text_match=800000),
        ]
        ranked = rerank_candidates(groups, "barre laser led")
        # Le full doit etre premier malgre son BM25 plus faible (pas de penalite)
        assert ranked[0]["doc"]["id_produit"] == "full"


class TestR2BrandAsHardFilter:
    """
    A8 R2 (2026-05-21) : si la query contient une marque connue + un type
    produit, le doc doit aussi couvrir le type (sinon penalite forte).

    Resout `urinoir delabie` -> Distributeur Delabie en pos 1 (matche marque
    mais pas le type).
    """

    def test_brand_only_no_r2_penalty(self):
        """Query avec seulement une marque (sans type) -> R2 inactif."""
        with mock.patch.object(reranker, "brands_available", return_value=True), \
             mock.patch.object(reranker, "split_query_brand_type",
                               return_value=({"delabie"}, set())):
            groups = [
                make_group("any", "Distributeur Delabie", "Distributeurs",
                           vec_dist=0.3, text_match=400000),
            ]
            ranked = rerank_candidates(groups, "delabie")
            # R2 inactif (pas de type token) -> pas de missing_type_with_brand
            assert "missing_type_with_brand" not in ranked[0]["penalty"]
            assert ranked[0]["r2_missing_type"] is False

    def test_brand_plus_type_missing_in_doc_strong_penalty(self):
        """Query brand+type, doc matche brand mais pas type -> penalite R2 forte."""
        with mock.patch.object(reranker, "brands_available", return_value=True), \
             mock.patch.object(reranker, "split_query_brand_type",
                               return_value=({"delabie"}, {"urinoir"})):
            groups = [
                # Doc matche "delabie" mais pas "urinoir"
                make_group("distributeur", "Distributeur Essuie Mains Hypereco Delabie",
                           "Distributeurs", vec_dist=0.3, text_match=900000),
            ]
            ranked = rerank_candidates(groups, "urinoir delabie")
            assert ranked[0]["r2_missing_type"] is True
            assert "missing_type_with_brand" in ranked[0]["penalty"]

    def test_brand_plus_type_both_in_doc_no_penalty(self):
        """Query brand+type, doc matche les deux -> pas de penalite R2."""
        with mock.patch.object(reranker, "brands_available", return_value=True), \
             mock.patch.object(reranker, "split_query_brand_type",
                               return_value=({"delabie"}, {"urinoir"})):
            groups = [
                # Doc matche "urinoir" ET "delabie"
                make_group("urinoir_delabie", "Urinoir Delabie inox suspendu",
                           "Urinoirs", vec_dist=0.3, text_match=500000),
            ]
            ranked = rerank_candidates(groups, "urinoir delabie")
            assert ranked[0]["r2_missing_type"] is False
            assert "missing_type_with_brand" not in ranked[0]["penalty"]

    def test_brand_with_type_match_via_categorie(self):
        """Le type peut etre couvert via la categorie (pas seulement nom_produit).

        Note : ici la categorie est "Urinoir" (singulier exact). Si la cat
        est "Urinoirs" pluriel, faut un synonyme `urinoir↔urinoirs` (gere
        par les clusters Typesense en prod, non actif dans ce test unitaire).
        """
        with mock.patch.object(reranker, "brands_available", return_value=True), \
             mock.patch.object(reranker, "split_query_brand_type",
                               return_value=({"delabie"}, {"urinoir"})):
            groups = [
                # Le nom_produit contient "delabie" mais pas "urinoir"
                # MAIS la categorie est "Urinoir" -> type couvert via cat
                make_group("delabie_cat_urinoir", "Modele Premium Delabie",
                           "Urinoir suspendu", vec_dist=0.3, text_match=500000),
            ]
            ranked = rerank_candidates(groups, "urinoir delabie")
            assert ranked[0]["r2_missing_type"] is False

    def test_r2_full_e2e_urinoir_delabie_correct_order(self):
        """
        E2E : sur "urinoir delabie", le vrai urinoir doit passer devant
        le distributeur essuie-mains (penalite R2 forte sur le distributeur).
        """
        with mock.patch.object(reranker, "brands_available", return_value=True), \
             mock.patch.object(reranker, "split_query_brand_type",
                               return_value=({"delabie"}, {"urinoir"})):
            groups = [
                # Distributeur essuie-mains Delabie : BM25 elevé sur "delabie" + "distributeur"
                make_group("distributeur", "Distributeur Essuie Mains Hypereco Delabie",
                           "Distributeurs", vec_dist=0.3, text_match=900000),
                # Urinoir Delabie : BM25 plus moyen mais matche les 2 tokens
                make_group("urinoir", "Urinoir Delabie inox", "Urinoirs",
                           vec_dist=0.3, text_match=400000),
            ]
            ranked = rerank_candidates(groups, "urinoir delabie")
            # Avec R2 : le vrai urinoir doit etre premier malgre son BM25 plus faible
            assert ranked[0]["doc"]["id_produit"] == "urinoir"
