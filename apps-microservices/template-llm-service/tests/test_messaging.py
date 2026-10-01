"""Consumer de template-llm-service : dépôt en tampon et garde tarifaire DeepSeek.

Réécrit le 20-08-2026. La version précédente patchait
`app.messaging.consumer.get_qualifier_service` — un symbole **qui n'existe pas** — et
appelait `consumer._on_message_callback(channel, method, props, body)`, la signature de
l'API `pika` **synchrone**. Le service utilise `aio_pika` : le vrai callback est
`async _on_message(message)`, et il ne fait que déposer le message dans un tampon.
Le test échouait donc à la collecte, et personne ne l'a vu parce que le fichier
`conftest.py` du répertoire était mal orthographié (`confest.py`).

Tests **synchrones** qui pilotent une boucle asyncio via `asyncio.run()` :
`pytest-asyncio` n'est déclaré dans aucun `requirements*.txt` de ce dépôt et aucun
`asyncio_mode` n'est configuré, donc `@pytest.mark.asyncio` serait muet ou en erreur.

Ce qui est prouvé ici tourne **sans broker**, donc partout. L'effet réel de la garde sur
les messages (rien perdu, rien en DLQ, tampon vidé, reprise) est prouvé contre un vrai
RabbitMQ dans `test_integration_garde_callback.py`.
"""
import asyncio
import json

import pytest

from app.messaging import consumer as mod
from app.messaging.consumer import Consumer


class FausseFile:
    """File minimale : enregistre les abonnements et les annulations.

    Écrite à la main plutôt qu'en `AsyncMock` pour que les assertions portent sur une
    séquence d'appels lisible, et pour pouvoir faire échouer `cancel` à la demande.
    """

    def __init__(self, echec_cancel=None):
        self.appels = []          # ('consume', tag) | ('cancel', tag)
        self._n = 0
        self._echec_cancel = echec_cancel

    async def consume(self, callback):
        self._n += 1
        tag = "tag-%d" % self._n
        self.appels.append(("consume", tag))
        return tag

    async def cancel(self, tag):
        if self._echec_cancel is not None:
            raise self._echec_cancel
        self.appels.append(("cancel", tag))

    # utilitaires de lecture
    def nb(self, quoi):
        return sum(1 for a in self.appels if a[0] == quoi)


def _consumer():
    """Consumer instancié sans connexion réelle : on ne teste que le messaging."""
    return Consumer(connection=object(), publisher=object())


# --- le vrai callback : il ne fait QUE remplir le tampon --------------------------


def test_on_message_depose_dans_le_tampon_sans_acquitter():
    """`_on_message` doit être léger : pas de traitement, pas d'ack.

    C'est ce qui permet à la garde de fonctionner : le message est mis de côté et
    l'acquittement n'a lieu qu'après traitement, dans `batch_processor`.
    """
    class FauxMessage:
        def __init__(self, corps):
            self.body = corps
            self.acquitte = False

        async def ack(self):
            self.acquitte = True

    async def scenario():
        c = _consumer()
        m = FauxMessage(json.dumps({"collection": "site", "url": "http://x"}).encode())
        await c._on_message(m)
        return c, m

    c, m = asyncio.run(scenario())
    assert c.message_buffer.qsize() == 1
    assert c.message_buffer.get_nowait() is m
    assert m.acquitte is False, "_on_message ne doit pas acquitter : le tampon attend"


# --- la garde tarifaire ----------------------------------------------------------


def _lancer_garde(monkeypatch, sequence, tours=None, echec_cancel=None):
    """Fait tourner la boucle de garde sur une séquence de verdicts horaires.

    `sequence` est une liste de booléens consommée un par tour ; la dernière valeur est
    répétée ensuite. Retourne (FausseFile, exception levée ou None).
    """
    etat = {"i": 0}

    def faux_est_heure_pleine(*_a, **_k):
        i = etat["i"]
        etat["i"] += 1
        return sequence[i] if i < len(sequence) else sequence[-1]

    monkeypatch.setattr(mod, "est_heure_pleine", faux_est_heure_pleine)
    monkeypatch.setattr(mod, "libelle_fenetre", lambda *_a, **_k: "fenetre de test")
    monkeypatch.setattr(mod, "ATTENTE_FENETRE_PLEINE_S", 0.01)

    file = FausseFile(echec_cancel=echec_cancel)
    limite = tours if tours is not None else len(sequence) + 1

    async def scenario():
        c = _consumer()
        tache = asyncio.create_task(c._boucle_fenetre_tarifaire(file))
        # on laisse passer `limite` tours de boucle (0.01 s chacun) avec de la marge
        for _ in range(400):
            if etat["i"] >= limite or tache.done():
                break
            await asyncio.sleep(0.005)
        if tache.done():
            return tache.exception()
        tache.cancel()
        try:
            await tache
        except asyncio.CancelledError:
            pass
        return None

    return file, asyncio.run(scenario())


def test_sabonne_en_heures_creuses(monkeypatch):
    """Heures creuses : un abonnement, et un seul — pas un par tour de boucle."""
    file, exc = _lancer_garde(monkeypatch, [False], tours=6)
    assert exc is None
    assert file.nb("consume") == 1, "la boucle se réabonne à chaque tour : %s" % file.appels
    assert file.nb("cancel") == 0


def test_se_desabonne_a_l_entree_en_fenetre_chere(monkeypatch):
    """Une seule annulation à la bascule, pas une par tour pendant toute la fenêtre."""
    file, exc = _lancer_garde(monkeypatch, [False, True], tours=8)
    assert exc is None
    assert file.nb("consume") == 1
    assert file.nb("cancel") == 1, "annulation répétée à chaque tour : %s" % file.appels
    assert file.appels[0][0] == "consume"
    assert file.appels[1][0] == "cancel"
    assert file.appels[0][1] == file.appels[1][1], "le tag annulé n'est pas celui reçu"


def test_ne_se_reabonne_pas_pendant_la_fenetre(monkeypatch):
    """Tant que la fenêtre dure, aucun nouvel abonnement — c'est tout l'objet de la garde."""
    file, exc = _lancer_garde(monkeypatch, [False, True], tours=15)
    assert exc is None
    assert file.nb("consume") == 1, "réabonnement en pleine fenêtre chère : %s" % file.appels


def test_se_reabonne_a_la_sortie_de_la_fenetre(monkeypatch):
    """Retour en heures creuses : réabonnement, et un tag neuf est mémorisé."""
    file, exc = _lancer_garde(monkeypatch, [False, True, True, False], tours=8)
    assert exc is None
    assert file.nb("consume") == 2, "pas de reprise après la fenêtre : %s" % file.appels
    assert file.nb("cancel") == 1
    consumes = [a[1] for a in file.appels if a[0] == "consume"]
    assert consumes[0] != consumes[1], "le second abonnement doit avoir son propre tag"


def test_une_erreur_de_canal_REMONTE(monkeypatch):
    """Le point qui a coûté une correction : la garde ne doit pas avaler ces erreurs.

    Mesuré le 20-08-2026 contre un vrai broker : une version qui attrapait tout et
    retentait laissait `queue` attachée au canal mort après une coupure, et retentait à
    l'infini — service muet, rien en DLQ, aucune alerte. `main.py` attrape déjà
    `(AMQPConnectionError, ChannelInvalidStateError)` et reconstruit connexion +
    consumer : il faut donc laisser passer l'exception. C'est aussi pourquoi la boucle
    est awaitée dans `start_consuming()` et non lancée en `create_task()`.
    """
    class ErreurCanalFactice(Exception):
        pass

    file, exc = _lancer_garde(
        monkeypatch, [False, True], tours=8, echec_cancel=ErreurCanalFactice("canal mort"))
    assert isinstance(exc, ErreurCanalFactice), (
        "la garde a avalé l'erreur de canal (exception remontée : %r) — elle boucherait "
        "en silence sur un canal mort" % exc)


def test_le_tag_est_bien_memorise_sur_l_instance(monkeypatch):
    """`queue.consume()` retourne un tag ; il était jeté avant cette correction."""
    monkeypatch.setattr(mod, "est_heure_pleine", lambda *_a, **_k: False)
    monkeypatch.setattr(mod, "libelle_fenetre", lambda *_a, **_k: "fenetre de test")
    monkeypatch.setattr(mod, "ATTENTE_FENETRE_PLEINE_S", 0.01)

    async def scenario():
        c = _consumer()
        assert c._consumer_tag is None, "le tag doit démarrer à None"
        tache = asyncio.create_task(c._boucle_fenetre_tarifaire(FausseFile()))
        for _ in range(200):
            if c._consumer_tag is not None:
                break
            await asyncio.sleep(0.005)
        tag = c._consumer_tag
        tache.cancel()
        try:
            await tache
        except asyncio.CancelledError:
            pass
        return tag

    assert asyncio.run(scenario()) == "tag-1"


def test_la_garde_utilisee_est_la_vraie():
    """Anti-faux-vert : si `common_utils` était stubbé, ce serait un MagicMock.

    Un MagicMock est vrai en contexte booléen : la garde se croirait en heure pleine à
    toute heure et les tests ci-dessus passeraient sans rien prouver.
    """
    import inspect
    assert inspect.isfunction(mod.est_heure_pleine), (
        "est_heure_pleine n'est pas une vraie fonction (%r) — common_utils est stubbé"
        % type(mod.est_heure_pleine))
    assert mod.est_heure_pleine.__module__ == "common_utils.autres.fenetre_tarifaire"
