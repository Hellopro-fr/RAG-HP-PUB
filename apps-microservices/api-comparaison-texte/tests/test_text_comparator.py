from app.core.text_comparator import compare_texts


def test_identical_texts():
    r = compare_texts("abc", "abc")
    assert r["similarity_ratio"] == 1.0
    assert r["decision"] == "SKIP"


def test_completely_different():
    r = compare_texts("abcdef", "xyzwvu")
    assert r["similarity_ratio"] < 0.85
    assert r["decision"] == "UPDATE"


def test_empty_strings():
    r = compare_texts("", "")
    assert r["similarity_ratio"] == 1.0
    assert r["decision"] == "SKIP"


def test_one_empty_one_filled():
    r = compare_texts("", "du texte ici")
    assert r["similarity_ratio"] == 0.0
    assert r["decision"] == "UPDATE"


def test_custom_threshold_strict():
    """Avec un seuil très strict (0.99), un texte quasi-identique → UPDATE."""
    r = compare_texts("hello world", "hello worl", threshold=0.99)
    assert r["decision"] == "UPDATE"


def test_custom_threshold_relaxed():
    """Avec un seuil relâché (0.5), un texte modéré → SKIP."""
    r = compare_texts("hello world", "hello earth", threshold=0.5)
    assert r["decision"] == "SKIP"


def test_default_threshold_085():
    """Le seuil par défaut (0.85) est appliqué."""
    # Deux textes avec ~90% de similarité → SKIP
    r = compare_texts(
        "Le produit est disponible en rouge",
        "Le produit est disponible en bleu",
    )
    assert r["decision"] == "SKIP"
    assert r["similarity_ratio"] >= 0.85


def test_ratio_precision():
    """Le ratio est arrondi à 4 décimales."""
    r = compare_texts("abc", "abd")
    assert isinstance(r["similarity_ratio"], float)
    ratio_str = str(r["similarity_ratio"])
    if "." in ratio_str:
        decimals = len(ratio_str.split(".")[1])
        assert decimals <= 4
