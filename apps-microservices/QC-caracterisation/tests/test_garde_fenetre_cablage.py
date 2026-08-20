"""Le consumer utilise-t-il la VRAIE garde tarifaire, ou un faux objet ?

Les bornes de la fenêtre sont testées dans `libs/common-utils/tests/test_fenetre_tarifaire.py`
(13 tests). Ce fichier-ci teste autre chose, propre au service : le **câblage**.

Pourquoi il existe. Le `conftest.py` de ce répertoire installe un `_FakeFinder` sur
`sys.meta_path` qui remplace `common_utils` par un `MagicMock` **quand la bibliothèque
n'est pas installée** (cas courant en local, sans `pip install -e libs/common-utils`).
Un `MagicMock` est vrai en contexte booléen : `est_heure_pleine()` renverrait donc un
objet *truthy* à toute heure, la garde suspendrait en permanence, et un test de la boucle
afficherait vert sans avoir rien prouvé.

Ces deux tests échouent bruyamment dans ce cas, au lieu de laisser passer un faux vert.
"""

import inspect

import pytest


def test_le_consumer_importe_la_vraie_garde():
    """`est_heure_pleine` doit être une fonction, et venir de common_utils.autres."""
    from app.messaging import consumer

    fonction = consumer.est_heure_pleine
    assert inspect.isfunction(fonction), (
        "est_heure_pleine n'est pas une vraie fonction (%r) : common_utils est "
        "probablement stubbé par le conftest. Lancer "
        "`pip install -e libs/common-utils` avant les tests de la garde."
        % type(fonction)
    )
    assert fonction.__module__ == "common_utils.autres.fenetre_tarifaire", (
        "est_heure_pleine vient de %s au lieu de common_utils.autres.fenetre_tarifaire"
        % fonction.__module__
    )


def test_les_deux_consumers_partagent_la_meme_garde():
    """Le module a été remonté dans `libs/` justement pour ne pas être dupliqué.

    Si un jour quelqu'un recrée un `app/core/fenetre_tarifaire.py` local, les deux
    consumers pourraient diverger sans que rien ne le signale.
    """
    from app.messaging import consumer, consumer_bo

    assert consumer.est_heure_pleine is consumer_bo.est_heure_pleine
    assert consumer.libelle_fenetre is consumer_bo.libelle_fenetre

    with pytest.raises(ImportError):
        import importlib

        importlib.import_module("app.core.fenetre_tarifaire")


def test_la_garde_repond_vraiment_sur_les_bornes():
    """Contrôle de bout en bout : une heure pleine et une heure creuse connues.

    Doublon assumé avec les tests de `libs/`, et c'est le but : si le câblage passe par
    un faux objet, celui-ci répondrait *truthy* aux deux appels et ce test le verrait.
    """
    from datetime import datetime, timezone

    from app.messaging import consumer

    pleine = datetime(2026, 8, 18, 2, tzinfo=timezone.utc)   # 02:00 UTC -> tarif double
    creuse = datetime(2026, 8, 18, 12, tzinfo=timezone.utc)  # 12:00 UTC -> moitié prix

    assert consumer.est_heure_pleine(pleine) is True
    assert consumer.est_heure_pleine(creuse) is False
