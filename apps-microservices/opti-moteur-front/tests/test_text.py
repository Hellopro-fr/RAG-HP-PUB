"""Tests unitaires des helpers text (tokenize, normalize, is_prefix_match)."""
from app.utils.text import normalize, tokenize, tokenize_ordered, is_prefix_match


class TestNormalize:
    def test_lowercase_and_accents(self):
        assert normalize("Armoire Médicale") == "armoire medicale"

    def test_empty(self):
        assert normalize("") == ""
        assert normalize(None) == ""


class TestTokenize:
    def test_basic(self):
        assert tokenize("Armoire Médicale") == {"armoire", "medicale"}

    def test_min_length_2(self):
        # "a" et "la" sont < 2 ou 2 chars
        assert tokenize("a la maison") == {"la", "maison"}

    def test_ordered_preserves_order(self):
        assert tokenize_ordered("Armoire Médicale Refrigeree") == ["armoire", "medicale", "refrigeree"]


class TestPrefixMatch:
    def test_exact_match(self):
        q = tokenize("armoire medicale")
        assert is_prefix_match(q, "Armoire médicale")
        assert is_prefix_match(q, "Armoire médicale réfrigérée")  # 3e mot en lookahead

    def test_reject_deep_position(self):
        # Les query tokens sont au-dela du lookahead (>= 4 mots avant) -> REJETE
        q = tokenize("armoire medicale")
        assert not is_prefix_match(q, "Mobilier de rangement pour armoire medicale")  # pos 4,5 hors lookahead=2

    def test_plural_tolerance(self):
        # signalisation vs signalisations (pluriel)
        q = tokenize("signalisation securite")
        assert is_prefix_match(q, "Signalisations sécurité travail")

    def test_reject_cascade(self):
        # Batterie lithium ne doit PAS matcher une categorie type "Armoire ..."
        q = tokenize("batterie lithium")
        assert not is_prefix_match(q, "Armoire de stockage batterie lithium")
        assert not is_prefix_match(q, "Batterie industrielle")  # lithium absent

    def test_partial_match_below_threshold(self):
        # Si seulement 1 token sur 2 matche en prefix, retourne False
        q = tokenize("perceuse 18V")
        assert not is_prefix_match(q, "Perceuse à colonne")  # "18v" absent
