"""Tests unitaires du loader IDF (A4)."""
import json

from app.services import idf_loader


def test_idf_unavailable_when_file_missing(tmp_path, monkeypatch):
    """Aucun fichier -> idf_available()=False, get_idf retourne la mediane (1.0)."""
    missing = tmp_path / "no_idf.json"
    monkeypatch.setattr(idf_loader, "_IDF_PATH", missing)
    idf_loader.reset_cache_for_test()

    assert idf_loader.idf_available() is False
    assert idf_loader.get_idf("anything") == 1.0  # mediane par defaut


def test_idf_loaded_with_full_format(tmp_path, monkeypatch):
    """Format standard {idf, median, n_docs} : ok."""
    path = tmp_path / "idf.json"
    payload = {
        "n_docs": 100000,
        "n_tokens": 3,
        "median": 2.5,
        "idf": {"melangeur": 1.2, "conique": 4.8, "armoire": 2.0},
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(idf_loader, "_IDF_PATH", path)
    idf_loader.reset_cache_for_test()

    assert idf_loader.idf_available() is True
    assert idf_loader.get_idf("conique") == 4.8
    assert idf_loader.get_idf("melangeur") == 1.2
    # Token inconnu -> mediane
    assert idf_loader.get_idf("inconnu") == 2.5


def test_idf_loaded_with_flat_format(tmp_path, monkeypatch):
    """Tolere aussi un format flat (dict token->float direct)."""
    path = tmp_path / "idf_flat.json"
    payload = {"foo": 3.0, "bar": 1.0, "baz": 5.0}
    path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(idf_loader, "_IDF_PATH", path)
    idf_loader.reset_cache_for_test()

    assert idf_loader.idf_available() is True
    assert idf_loader.get_idf("foo") == 3.0
    # Mediane calculee sur [1.0, 3.0, 5.0] = 3.0
    assert idf_loader.get_idf("not_present") == 3.0


def test_idf_corrupt_file_fallbacks(tmp_path, monkeypatch):
    """JSON corrompu -> idf_available()=False, pas de crash."""
    path = tmp_path / "broken.json"
    path.write_text("{not valid json", encoding="utf-8")
    monkeypatch.setattr(idf_loader, "_IDF_PATH", path)
    idf_loader.reset_cache_for_test()

    assert idf_loader.idf_available() is False
    # mediane = 1.0 (default) car aucun load
    assert idf_loader.get_idf("foo") == 1.0
