"""Tests unitaires du loader synonymes (A6)."""
from unittest import mock

from app.services import synonyms_loader


def _typesense_response(clusters):
    """Helper : construit la reponse Typesense {synonyms: [...]}."""
    return {"synonyms": clusters}


def test_no_synonyms_when_typesense_returns_empty(monkeypatch):
    """Typesense retourne 0 cluster -> mapping vide, synonyms_available()=False."""
    synonyms_loader.reset_cache_for_test()
    monkeypatch.setattr(
        synonyms_loader.typesense_client,
        "list_synonyms",
        lambda **kw: _typesense_response([]),
    )
    assert synonyms_loader.synonyms_available() is False
    assert synonyms_loader.get_synonyms_map() == {}
    # expand_tokens doit retourner les tokens inchanges
    assert synonyms_loader.expand_tokens({"crane"}) == {"crane"}


def test_no_synonyms_when_typesense_fails(monkeypatch):
    """Typesense leve une exception -> fallback silencieux sur mapping vide."""
    synonyms_loader.reset_cache_for_test()

    def raise_exc(**kw):
        raise RuntimeError("Typesense unreachable")

    monkeypatch.setattr(synonyms_loader.typesense_client, "list_synonyms", raise_exc)
    assert synonyms_loader.synonyms_available() is False
    assert synonyms_loader.expand_tokens({"foo"}) == {"foo"}


def test_loads_synonyms_and_builds_mapping(monkeypatch):
    """Cas nominal : un cluster grue/crane est charge et mappe."""
    synonyms_loader.reset_cache_for_test()
    clusters = [
        {"id": "manual-grue", "synonyms": ["grue", "grues", "grutier", "crane", "cranes", "e-crane"]},
        {"id": "manual-medical", "synonyms": ["medical", "medicale", "medicaux", "medicales"]},
    ]
    monkeypatch.setattr(
        synonyms_loader.typesense_client,
        "list_synonyms",
        lambda **kw: _typesense_response(clusters),
    )

    assert synonyms_loader.synonyms_available() is True
    m = synonyms_loader.get_synonyms_map()

    # "crane" doit pointer vers le cluster complet (apres tokenize)
    # "e-crane" est tokenise en "crane" (e de longueur 1 est filtre)
    # donc le set effectif est {grue, grues, grutier, crane, cranes}
    assert "crane" in m
    assert m["crane"] == {"grue", "grues", "grutier", "crane", "cranes"}
    # symmetric : grue pointe aussi vers crane
    assert m["grue"] == {"grue", "grues", "grutier", "crane", "cranes"}
    # medical cluster
    assert m["medicale"] == {"medical", "medicale", "medicaux", "medicales"}


def test_expand_tokens_returns_union(monkeypatch):
    """expand_tokens({crane}) -> {crane, grue, grues, grutier, cranes}."""
    synonyms_loader.reset_cache_for_test()
    clusters = [{"id": "manual-grue", "synonyms": ["grue", "grues", "grutier", "crane", "cranes"]}]
    monkeypatch.setattr(
        synonyms_loader.typesense_client,
        "list_synonyms",
        lambda **kw: _typesense_response(clusters),
    )

    result = synonyms_loader.expand_tokens({"crane"})
    assert result == {"grue", "grues", "grutier", "crane", "cranes"}


def test_expand_tokens_unknown_token(monkeypatch):
    """Token absent du mapping -> retourne le set inchange."""
    synonyms_loader.reset_cache_for_test()
    clusters = [{"id": "manual-grue", "synonyms": ["grue", "crane"]}]
    monkeypatch.setattr(
        synonyms_loader.typesense_client,
        "list_synonyms",
        lambda **kw: _typesense_response(clusters),
    )

    # "perceuse" pas dans le mapping
    result = synonyms_loader.expand_tokens({"perceuse"})
    assert result == {"perceuse"}


def test_cluster_with_root_field(monkeypatch):
    """Cluster avec 'root' (one-way synonym) : root inclus dans le set."""
    synonyms_loader.reset_cache_for_test()
    clusters = [
        {"id": "manual-minipelle", "root": "minipelle", "synonyms": ["mini pelle", "mini-pelle"]},
    ]
    monkeypatch.setattr(
        synonyms_loader.typesense_client,
        "list_synonyms",
        lambda **kw: _typesense_response(clusters),
    )

    m = synonyms_loader.get_synonyms_map()
    # "minipelle" doit etre dans le mapping (vient du root + synonymes)
    # "mini-pelle" tokenize -> "mini" + "pelle"
    assert "minipelle" in m
    assert "pelle" in m
    # tous se referent au meme set
    assert "minipelle" in m["pelle"]
