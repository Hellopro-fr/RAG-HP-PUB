"""Bootstrap des tests de nettoyage-bruit-ocr-service.

Ce repertoire n'avait pas de conftest.py : `tests/test_processor.py` ne pouvait donc rien
importer du service, et il s'en passait en RECOPIANT la logique a tester. Ce fichier
rend `app/` importable, neutralise les dependances indisponibles hors Docker, et charge
la VRAIE garde tarifaire depuis le depot.

Modele : `QC-fabricant-reference/tests/conftest.py` (motif _FakeFinder du depot).
"""
import importlib.abc
import importlib.machinery
import importlib.util
import os
import sys
import types
from unittest.mock import MagicMock

_racine_service = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, _racine_service)

# Dans l'image, `app/` est monte sous le nom `nettoyage_bruit_ocr_service` (cf.
# docker-compose, volumes) : les modules du service s'importent mutuellement sous ce
# nom. En local le repertoire s'appelle `app`, d'ou cet alias.
if 'nettoyage_bruit_ocr_service' not in sys.modules:
    _init = os.path.join(_racine_service, 'app', '__init__.py')
    _spec = importlib.util.spec_from_file_location(
        'nettoyage_bruit_ocr_service',
        _init if os.path.exists(_init) else None,
        submodule_search_locations=[os.path.join(_racine_service, 'app')],
    )
    if _spec is not None:
        _mod = importlib.util.module_from_spec(_spec)
        sys.modules['nettoyage_bruit_ocr_service'] = _mod
        if _spec.loader is not None and os.path.exists(_init):
            _spec.loader.exec_module(_mod)

# Dependances externes stubbees si absentes (jamais si reellement installees).
_FAKE_ROOTS = ("common_utils", "grpc", "grpc_stubs", "aiormq", "aio_pika", "httpx")


class _FakeLoader(importlib.abc.Loader):
    def create_module(self, spec):
        mod = types.ModuleType(spec.name)
        mod.__path__ = []
        mod.__getattr__ = lambda name: MagicMock()
        return mod

    def exec_module(self, module):
        pass


class _FakeFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        root = fullname.split(".")[0]
        if root not in _FAKE_ROOTS:
            return None
        try:
            real = importlib.machinery.PathFinder.find_spec(fullname, path)
        except Exception:
            real = None
        if real is not None:
            return real
        return importlib.machinery.ModuleSpec(fullname, _FakeLoader(), is_package=True)


sys.meta_path.append(_FakeFinder())


# --- la garde tarifaire doit etre la VRAIE, jamais un MagicMock -------------------
# Un MagicMock est vrai en contexte booleen : la garde se croirait en heure pleine a
# TOUTE heure. `common_utils/autres/` etant un namespace package sans __init__.py et
# sans dependance hors stdlib, on peut charger ce seul module par chemin sans rien
# tirer d'autre -- passer par le package entier tirerait `grpc_clients` -> `grpc_stubs`,
# qui n'est genere qu'au build Docker.
_GARDE = "common_utils.autres.fenetre_tarifaire"
if _GARDE not in sys.modules:
    _racine_depot = os.path.dirname(os.path.dirname(_racine_service))
    _chemin = os.path.join(_racine_depot, "libs", "common-utils", "src",
                           "common_utils", "autres", "fenetre_tarifaire.py")
    assert os.path.exists(_chemin), (
        "garde tarifaire introuvable a %s : arborescence inattendue. Les tests de la "
        "garde tourneraient sur un MagicMock sans rien prouver." % _chemin
    )
    _s = importlib.util.spec_from_file_location(_GARDE, _chemin)
    _m = importlib.util.module_from_spec(_s)
    _s.loader.exec_module(_m)
    sys.modules[_GARDE] = _m
