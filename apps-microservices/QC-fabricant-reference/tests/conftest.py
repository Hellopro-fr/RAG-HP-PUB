"""
Neutralise les dependances externes du service (indisponibles hors Docker/CI)
pour permettre l'execution locale des tests unitaires.

En CI/Docker (ou common_utils, openai, tenacity, httpx sont installes), ces stubs
ne sont pas utilises : find_spec ne repond que pour les modules reellement absents.
"""
import sys
import types
import importlib.abc
import importlib.machinery
from unittest.mock import MagicMock

# Racines de packages externes a stubber si absents
_FAKE_ROOTS = ("common_utils", "openai", "tenacity", "httpx", "aio_pika")


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
        # Preferer le vrai module s'il est installe ; sinon stub
        try:
            real = importlib.machinery.PathFinder.find_spec(fullname, path)
        except Exception:
            real = None
        if real is not None:
            return real
        return importlib.machinery.ModuleSpec(fullname, _FakeLoader(), is_package=True)


# Inserer le finder en dernier recours (apres les finders standards)
sys.meta_path.append(_FakeFinder())

# Stub de la config : evite la lecture d'environnement reelle (DEEPSEEK_API_KEY, HP_TOKEN).
# Les valeurs numeriques sont explicites : un MagicMock casserait range()/int().
_cred = types.ModuleType("app.core.credentials")
_settings = MagicMock()
_settings.MAX_CONCURRENCY = 2
_settings.BATCH_PRODUITS = 10
_settings.APPELS_PARALLELES = 4
_settings.MAX_ECHECS_BATCH = 5
_settings.DEEPSEEK_API_KEY = "test-key"
_settings.DEEPSEEK_API_URL = "https://api.deepseek.com"
_settings.DEEPSEEK_MODEL_NAME = "deepseek-v4-flash"
_settings.HP_API_URL = "https://api.hellopro.fr/v2/index.php"
_settings.HP_TOKEN = "test-token"
_settings.PROMPT_EXTRACTION_ID = "133"
_settings.HP_TIMEOUT_SECONDS = 300
_cred.settings = _settings
sys.modules.setdefault("app.core.credentials", _cred)
