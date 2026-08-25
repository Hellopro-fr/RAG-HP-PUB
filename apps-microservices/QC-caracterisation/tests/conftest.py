"""
Neutralise les dépendances externes du service (indisponibles hors Docker/CI)
pour permettre l'exécution locale des tests unitaires de logique BO.

En CI/Docker (où common_utils, google, openai, tenacity, httpx sont installés),
ces stubs ne sont pas nécessaires mais restent inoffensifs (find_spec ne
répond que pour les modules réellement absents, via ImportError du vrai import).
"""
import os
import sys
import types
import importlib.abc
import importlib.machinery
import importlib.util
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


# --- la garde tarifaire doit être la VRAIE, jamais un MagicMock -------------------
#
# `common_utils` fait partie des racines stubbées ci-dessus : sans installation locale,
# `common_utils.autres.fenetre_tarifaire.est_heure_pleine` serait un MagicMock. Or un
# MagicMock est vrai en contexte booléen, donc la garde se croirait en heure pleine à
# TOUTE heure, et un test de la boucle afficherait vert sans rien prouver.
#
# On charge donc ce seul sous-module depuis le dépôt, par chemin de fichier. C'est sans
# risque : `common_utils/autres/` est un namespace package **sans `__init__.py` et sans
# dépendance hors stdlib** — le vérifier revient à constater qu'aucune dep lourde
# n'apparaît dans `sys.modules` après l'import. Passer par le package `common_utils`
# entier, lui, tirerait `grpc_clients` -> `grpc_stubs`, qui n'est généré qu'au build
# Docker (le Dockerfile le produit depuis `protos/` ; il n'existe pas en local, et il
# ne faut pas le générer ici — ce serait polluer le dépôt de fichiers non versionnés).
_GARDE = "common_utils.autres.fenetre_tarifaire"
if _GARDE not in sys.modules:
    _racine = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))))
    _chemin = os.path.join(_racine, "libs", "common-utils", "src",
                           "common_utils", "autres", "fenetre_tarifaire.py")
    if os.path.exists(_chemin):
        _spec = importlib.util.spec_from_file_location(_GARDE, _chemin)
        _module = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_module)
        sys.modules[_GARDE] = _module
    # Si le fichier est introuvable (arborescence inattendue), on ne masque rien :
    # `test_garde_fenetre_cablage.py` échouera en disant pourquoi.

# Stub de la config (évite la lecture d'environnement réelle)
_cred = types.ModuleType("app.core.credentials")
_settings = MagicMock()
_settings.MAX_CONCURRENCY = 2
_cred.settings = _settings
sys.modules.setdefault("app.core.credentials", _cred)
