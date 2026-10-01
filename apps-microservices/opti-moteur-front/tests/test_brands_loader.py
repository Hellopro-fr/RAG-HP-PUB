"""Tests unitaires du loader de marques (R2)."""
from app.services import brands_loader


def _typesense_facet_response(brand_values, fournisseur_values):
    """Helper : construit la reponse Typesense multi_search avec facets."""
    return {
        "results": [{
            "facet_counts": [
                {"field_name": "marque", "counts": [{"value": v, "count": 1} for v in brand_values]},
                {"field_name": "fournisseur", "counts": [{"value": v, "count": 1} for v in fournisseur_values]},
            ],
        }],
    }


def test_no_brands_when_typesense_returns_empty(monkeypatch):
    brands_loader.reset_cache_for_test()
    monkeypatch.setattr(
        brands_loader.typesense_client,
        "multi_search",
        lambda body: _typesense_facet_response([], []),
    )
    assert brands_loader.brands_available() is False
    assert brands_loader.get_brands_set() == set()
    assert brands_loader.is_brand("delabie") is False


def test_no_brands_when_typesense_fails(monkeypatch):
    brands_loader.reset_cache_for_test()

    def raise_exc(body):
        raise RuntimeError("Typesense unreachable")

    monkeypatch.setattr(brands_loader.typesense_client, "multi_search", raise_exc)
    assert brands_loader.brands_available() is False
    assert brands_loader.is_brand("delabie") is False


def test_loads_single_token_brands(monkeypatch):
    """Marques mono-token : ajoutees au set. Marques multi-mots : skip."""
    brands_loader.reset_cache_for_test()
    monkeypatch.setattr(
        brands_loader.typesense_client,
        "multi_search",
        lambda body: _typesense_facet_response(
            ["DELABIE", "XCMG", "Saint Gobain"],  # 2 mono + 1 multi
            ["Zoomlion", "Liebherr", "Officity Z2"],  # 2 mono + 1 multi
        ),
    )
    assert brands_loader.brands_available() is True
    brands = brands_loader.get_brands_set()
    # Marques mono-token (normalisees lowercase, sans accent)
    assert "delabie" in brands
    assert "xcmg" in brands
    assert "zoomlion" in brands
    assert "liebherr" in brands
    # Multi-tokens : skipees pour l'instant
    assert "saint" not in brands or "gobain" not in brands


def test_is_brand_normalized(monkeypatch):
    """is_brand est case-insensitive et fold accents."""
    brands_loader.reset_cache_for_test()
    monkeypatch.setattr(
        brands_loader.typesense_client,
        "multi_search",
        lambda body: _typesense_facet_response(["DELABIE", "Liebherr"], []),
    )
    assert brands_loader.is_brand("delabie") is True
    assert brands_loader.is_brand("liebherr") is True
    assert brands_loader.is_brand("xcmg") is False


def test_split_query_brand_type(monkeypatch):
    """split_query_brand_type separe correctement brand vs type tokens."""
    brands_loader.reset_cache_for_test()
    monkeypatch.setattr(
        brands_loader.typesense_client,
        "multi_search",
        lambda body: _typesense_facet_response(["DELABIE", "Liebherr"], []),
    )

    # Query "urinoir delabie" -> brand={delabie}, type={urinoir}
    brand, type_ = brands_loader.split_query_brand_type({"urinoir", "delabie"})
    assert brand == {"delabie"}
    assert type_ == {"urinoir"}

    # Query "delabie" seule -> brand={delabie}, type={} (R2 inactif)
    brand, type_ = brands_loader.split_query_brand_type({"delabie"})
    assert brand == {"delabie"}
    assert type_ == set()

    # Query "armoire medicale" sans marque -> brand={}, type=tout
    brand, type_ = brands_loader.split_query_brand_type({"armoire", "medicale"})
    assert brand == set()
    assert type_ == {"armoire", "medicale"}
