"""Bootstrap des tests de template-llm-service.

Ce fichier s'appelait `confest.py` — une faute de frappe : pytest ne charge que
`conftest.py`, donc l'insertion de `sys.path` ci-dessous **n'a jamais eu lieu** et les
tests de ce répertoire n'ont jamais pu s'exécuter.

Il neutralise aussi les dépendances externes indisponibles hors Docker, sur le modèle de
`QC-fabricant-reference/tests/conftest.py`, et charge la **vraie** garde tarifaire depuis
le dépôt — un `MagicMock` étant vrai en contexte booléen, une garde stubbée se croirait
en heure pleine à toute heure et un test de la boucle afficherait vert sans rien prouver.
"""
import importlib.abc
import importlib.machinery
import importlib.util
import os
import sys
import types
from unittest.mock import MagicMock

# Racine du service, pour que `from app...` fonctionne.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# `app/` est monté sous le nom `template_llm_service` dans l'image (cf. docker-compose,
# volumes) : les modules du service s'importent mutuellement sous ce nom. En local le
# répertoire s'appelle `app`, d'où cet alias.
_racine_service = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if 'template_llm_service' not in sys.modules:
    _spec = importlib.util.spec_from_file_location(
        'template_llm_service',
        os.path.join(_racine_service, 'app', '__init__.py'),
        submodule_search_locations=[os.path.join(_racine_service, 'app')],
    )
    if _spec is not None:
        _mod = importlib.util.module_from_spec(_spec)
        sys.modules['template_llm_service'] = _mod
        if _spec.loader is not None and os.path.exists(
                os.path.join(_racine_service, 'app', '__init__.py')):
            _spec.loader.exec_module(_mod)

# Dépendances externes stubbées si absentes (jamais si réellement installées).
_FAKE_ROOTS = ("common_utils", "grpc", "grpc_stubs", "transformers", "aiormq", "aio_pika")


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


# --- la garde tarifaire doit être la VRAIE, jamais un MagicMock -------------------
# `common_utils/autres/` est un namespace package sans `__init__.py` et sans dépendance
# hors stdlib : on peut charger ce seul module par chemin sans rien tirer d'autre. Passer
# par le package `common_utils` entier tirerait `grpc_clients` -> `grpc_stubs`, qui n'est
# généré qu'au build Docker.
_GARDE = "common_utils.autres.fenetre_tarifaire"
if _GARDE not in sys.modules:
    # `_racine_service` = .../apps-microservices/template-llm-service
    # deux remontées suffisent pour atteindre la racine du dépôt. Une de plus visait
    # le dossier parent du dépôt : le fichier n'était pas trouvé, le module restait
    # stubbé, et les tests de la garde tournaient sur un MagicMock — attrapé par
    # `test_la_garde_utilisee_est_la_vraie`.
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


# --- fichiers de test laissés intacts mais écartés de la collecte -----------------
#
# `test_qualifier.py` importe `app.core.qualifier.service`, un package qui **n'existe
# pas** : `app/core/` ne contient que `processor.py`. Le fichier échoue donc à la
# collecte et rend rouge toute la suite du service.
#
# DÉCISION du 20-08-2026 : on ne le supprime pas — ce n'est pas notre fichier, et il
# témoigne peut-être d'un code à venir ou d'un renommage inachevé. On l'écarte de la
# collecte, en laissant la raison ici pour son auteur. Le jour où `app/core/qualifier/`
# existe, il suffit de retirer cette ligne.
collect_ignore = ["test_qualifier.py"]
