"""
Neutralise les dépendances externes du service (indisponibles hors Docker/CI)
pour permettre l'exécution locale des tests unitaires de logique BO.

En CI/Docker (où common_utils, google, openai, tenacity, httpx sont installés),
ces stubs ne sont pas nécessaires mais restent inoffensifs (find_spec ne
répond que pour les modules réellement absents, via ImportError du vrai import).
"""
import sys
import types
import importlib.abc
import importlib.machinery
from unittest.mock import MagicMock

# Racines de packages externes à stubber si absents
_FAKE_ROOTS = ("common_utils", "google", "openai", "tenacity", "httpx")


class _FakeLoader(importlib.abc.Loader):
    def create_module(self, spec):
        mod = types.ModuleType(spec.name)
        mod.__path__ = []  # package factice (autorise les sous-modules)
        mod.__getattr__ = lambda name: MagicMock()
        return mod

    def exec_module(self, module):
        pass


class _FakeFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        root = fullname.split(".")[0]
        if root not in _FAKE_ROOTS:
            return None
        # Préférer le vrai module s'il est installé ; sinon stub
        try:
            real = importlib.machinery.PathFinder.find_spec(fullname, path)
        except Exception:
            real = None
        if real is not None:
            return real
        return importlib.machinery.ModuleSpec(fullname, _FakeLoader(), is_package=True)


# Insérer le finder en dernier recours (après les finders standards)
sys.meta_path.append(_FakeFinder())

# Stub de la config (évite la lecture d'environnement réelle)
_cred = types.ModuleType("app.core.credentials")
_settings = MagicMock()
_settings.MAX_CONCURRENCY = 2
_cred.settings = _settings
sys.modules.setdefault("app.core.credentials", _cred)
