# -*- coding: utf-8 -*-
"""Test d'INTEGRATION de la garde heures creuses contre un VRAI broker RabbitMQ.

SAUTE par defaut. Pour l'executer, fournir un broker jetable :

    RABBITMQ_URL_TEST=amqp://user:pass@localhost:5672/ pytest tests/ -k integration -s

C'est le seul test qui prouve ce que la simulation ne peut pas : qu'une suspension ne
perd aucun message, n'en envoie aucun en DLQ et n'en duplique aucun. Il reproduit la
topologie exacte du service (exchange principal, retry TTL 30 s, DLQ, x-consumer-timeout)
et rejoue la boucle du consumer.

Il ne teste PAS l'integration avec caracterisation_produit : il isole la mecanique
RabbitMQ, qui etait le point en doute. Le calcul des heures est couvert par
test_fenetre_tarifaire.py.

GARDE-FOU : le test ECHOUE s'il n'a rien exerce. Premiere execution du 18-08-2026, le
traitement etait instantane, les 12 messages passaient AVANT la bascule et le test
affichait vert sans avoir jamais suspendu quoi que ce soit. D'ou DUREE_TRAITEMENT_S et
l'assertion sur le nombre de messages en attente pendant la pause.

Valide le 18-08-2026 contre RabbitMQ 3.12.1 avec aio_pika 9.6.2 (version de production) :
4 messages traites, 8 en attente pendant la pause, 0 en DLQ, 12/12 au retour, 0 doublon.
"""
import asyncio
import os

import pytest

URL = os.environ.get('RABBITMQ_URL_TEST')

pytestmark = pytest.mark.skipif(
    not URL,
    reason="definir RABBITMQ_URL_TEST pour lancer ce test (broker jetable requis)",
)

aio_pika = pytest.importorskip('aio_pika')

PREFIXE = 'test_garde_heures_creuses'
QUEUE = PREFIXE + '_queue'
QUEUE_RETRY = QUEUE + '_retry'
QUEUE_DLQ = QUEUE + '_dlq'
EXCHANGE = PREFIXE + '_exchange'
EXCHANGE_RETRY = PREFIXE + '_retry_exchange'
EXCHANGE_DLQ = PREFIXE + '_dlq_exchange'
ROUTING = 'test.garde.start'

RETRY_TTL_MS = 30000          # identique au service
MAX_CONCURRENCY = 10          # prefetch_count identique au service
# Il en faut BIEN PLUS que le prefetch. Depuis que ce test exerce la boucle reelle, le
# traitement est CONCURRENT (`create_task`, comme en production) et non plus sequentiel :
# les premiers messages partent tous en vol d'un coup. Avec 12 messages et un prefetch
# de 10, il n'en restait aucun en file au moment de la bascule et le garde-fou
# anti-faux-vert refusait le test -- a juste titre, il n'y avait rien a suspendre.
NB_MESSAGES = 30
DUREE_TRAITEMENT_S = 0.4      # simule la duree d'un appel LLM
BASCULE_APRES = 3             # nb de messages traites avant de forcer l'heure pleine

# fenetre pilotable a chaud par le test (le module lit l'env une fois ; ici on pilote
# directement le predicat pour rejouer une bascule)
etat = {'pleine': False}


def est_heure_pleine():
    return etat['pleine']


async def declarer(channel):
    """Topologie identique a celle du service."""
    ex_dlq = await channel.declare_exchange(EXCHANGE_DLQ, aio_pika.ExchangeType.TOPIC, durable=True)
    q_dlq = await channel.declare_queue(QUEUE_DLQ, durable=True)
    await q_dlq.bind(ex_dlq, routing_key=ROUTING)

    ex_retry = await channel.declare_exchange(EXCHANGE_RETRY, aio_pika.ExchangeType.TOPIC, durable=True)
    q_retry = await channel.declare_queue(
        QUEUE_RETRY, durable=True,
        arguments={'x-message-ttl': RETRY_TTL_MS,
                   'x-dead-letter-exchange': EXCHANGE,
                   'x-dead-letter-routing-key': ROUTING})
    await q_retry.bind(ex_retry, routing_key=ROUTING)

    ex = await channel.declare_exchange(EXCHANGE, aio_pika.ExchangeType.TOPIC, durable=True)
    q = await channel.declare_queue(
        QUEUE, durable=True,
        arguments={'x-dead-letter-exchange': EXCHANGE_RETRY,
                   'x-dead-letter-routing-key': ROUTING,
                   'x-consumer-timeout': 7200000})
    await q.bind(ex, routing_key=ROUTING)
    return ex, q, q_dlq


async def compter(connexion, nom):
    """Profondeur d'une file, lue par une declaration passive."""
    ch = await connexion.channel()
    try:
        q = await ch.declare_queue(nom, passive=True)
        return q.declaration_result.message_count
    finally:
        await ch.close()


async def consommer(queue, traites, arret):
    """Exerce la BOUCLE REELLE du service : `Consumer.consommer_avec_garde`.

    Ce test rejouait auparavant une copie de cette boucle (« COPIE FIDELE de la boucle
    posee dans consumer.py »). Une copie peut rester verte alors que le code livre a
    change : la boucle a donc ete extraite dans une methode, que ce test appelle.

    Seuls le predicat horaire et le traitement sont injectes :
      - `est_heure_pleine` est remplace dans le module du consumer, pour pouvoir
        basculer a la demande sans attendre 1 h du matin ;
      - `sur_message` simule un appel LLM d'une duree NON NULLE. Sans cela la file se
        vide avant la bascule et le test ne prouve rien (constate le 18-08-2026 :
        12/12 traites avant la bascule, test vert sans avoir rien suspendu).
    """
    from app.messaging import consumer as mod

    mod.est_heure_pleine = est_heure_pleine          # predicat pilote par le test
    mod.libelle_fenetre = lambda *_a, **_k: 'fenetre de test'
    mod.ATTENTE_FENETRE_PLEINE_S = 0.2               # 60 s en production

    async def traiter(message):
        await asyncio.sleep(DUREE_TRAITEMENT_S)
        traites.append(message.body.decode())
        await message.ack()

    taches = set()

    def sur_message(message):
        t = asyncio.create_task(traiter(message))
        taches.add(t)
        t.add_done_callback(taches.discard)

    instance = mod.Consumer.__new__(mod.Consumer)     # pas de connexion reelle requise
    await instance.consommer_avec_garde(queue, sur_message)


async def main():
    print('=' * 96)
    print('TEST D\'INTEGRATION -- garde heures creuses contre un VRAI RabbitMQ')
    print('  broker    :', URL.replace('guest:guest', 'guest:***'))
    print('  aio_pika  :', aio_pika.__version__)
    print('=' * 96)

    connexion = await aio_pika.connect_robust(URL)
    channel = await connexion.channel()
    await channel.set_qos(prefetch_count=MAX_CONCURRENCY)

    # table rase entre deux executions
    for nom in (QUEUE, QUEUE_RETRY, QUEUE_DLQ):
        try:
            q = await channel.declare_queue(nom, passive=True)
            await q.purge()
        except Exception:
            channel = await connexion.channel()
            await channel.set_qos(prefetch_count=MAX_CONCURRENCY)

    exchange, queue, queue_dlq = await declarer(channel)

    for i in range(1, NB_MESSAGES + 1):
        await exchange.publish(
            aio_pika.Message(body=f'm{i}'.encode(),
                             delivery_mode=aio_pika.DeliveryMode.PERSISTENT),
            routing_key=ROUTING)
    print(f'\n{NB_MESSAGES} messages publies (prefetch_count={MAX_CONCURRENCY})')

    traites = []
    arret = asyncio.Event()
    echecs = []

    # --- phase 1 : heures CREUSES, on laisse passer 4 messages
    etat['pleine'] = False
    tache = asyncio.create_task(consommer(queue, traites, arret))
    while len(traites) < BASCULE_APRES:
        await asyncio.sleep(0.05)

    # --- phase 2 : BASCULE en heures pleines
    etat['pleine'] = True
    await asyncio.sleep(1.5)                  # laisse la boucle se detacher
    apres_bascule = len(traites)
    await asyncio.sleep(2.0)                  # rien ne doit bouger pendant ce temps

    en_file = await compter(connexion, QUEUE)
    en_dlq = await compter(connexion, QUEUE_DLQ)
    en_retry = await compter(connexion, QUEUE_RETRY)
    fige = len(traites) == apres_bascule

    print('\n--- PENDANT la fenetre pleine ---')
    print('  traites avant bascule ......... %d' % apres_bascule)
    print('  traites pendant la pause ...... %d   %s' % (
        len(traites) - apres_bascule, 'OK (aucun)' if fige else 'ECHEC'))
    print('  messages READY dans la file ... %d   %s' % (
        en_file, 'OK (la suspension a bien ete exercee)' if en_file
        else 'TEST NON CONCLUANT -- file vide, rien a suspendre'))
    print('  messages en RETRY ............. %d   %s' % (
        en_retry, 'OK' if en_retry == 0 else 'ECHEC -- passes par le retry !'))
    print('  messages en DLQ ............... %d   %s' % (
        en_dlq, 'OK (aucun)' if en_dlq == 0 else 'ECHEC -- messages jetes !'))
    if en_file == 0:
        echecs.append(
            "TEST NON CONCLUANT : aucun message n'attendait en file pendant la pause, "
            "la suspension n'a donc pas ete exercee (augmenter NB_MESSAGES ou "
            "DUREE_TRAITEMENT_S)")
    if not fige:
        echecs.append('des messages ont ete traites pendant la fenetre pleine')
    if en_dlq:
        echecs.append('%d message(s) en DLQ' % en_dlq)
    if en_retry:
        echecs.append('%d message(s) partis en retry' % en_retry)
    perdus = NB_MESSAGES - apres_bascule - en_file
    print('  conservation .................. %d publies = %d traites + %d en file %s' % (
        NB_MESSAGES, apres_bascule, en_file,
        '(OK)' if perdus == 0 else '=> %d PERDUS' % perdus))
    if perdus != 0:
        echecs.append('%d message(s) ni traites ni en file' % perdus)

    # --- phase 3 : retour en heures creuses, tout doit passer
    etat['pleine'] = False
    for _ in range(120):
        if len(traites) >= NB_MESSAGES:
            break
        await asyncio.sleep(0.1)

    arret.set()
    etat['pleine'] = False
    await asyncio.sleep(0.3)
    tache.cancel()
    try:
        await tache
    except (asyncio.CancelledError, Exception):
        pass

    reste = await compter(connexion, QUEUE)
    dlq_fin = await compter(connexion, QUEUE_DLQ)
    doublons = len(traites) != len(set(traites))

    print('\n--- APRES retour en heures creuses ---')
    print('  total traites ................. %d / %d %s' % (
        len(traites), NB_MESSAGES, '(OK)' if len(traites) == NB_MESSAGES else '(INCOMPLET)'))
    print('  doublons ...................... %s' % ('AUCUN (OK)' if not doublons else 'OUI -- ECHEC'))
    print('  reste en file ................. %d' % reste)
    print('  DLQ finale .................... %d' % dlq_fin)
    manquants = sorted(set(f'm{i}' for i in range(1, NB_MESSAGES + 1)) - set(traites))
    if manquants:
        print('  MANQUANTS ..................... %s' % manquants)
        echecs.append('messages jamais traites : %s' % manquants)
    if doublons:
        echecs.append('messages traites en double')
    if dlq_fin:
        echecs.append('%d message(s) en DLQ a la fin' % dlq_fin)

    # nettoyage : on ne laisse rien derriere
    ch = await connexion.channel()
    for nom in (QUEUE, QUEUE_RETRY, QUEUE_DLQ):
        try:
            await (await ch.declare_queue(nom, passive=True)).delete(if_unused=False, if_empty=False)
        except Exception:
            ch = await connexion.channel()
    for nom in (EXCHANGE, EXCHANGE_RETRY, EXCHANGE_DLQ):
        try:
            await (await ch.declare_exchange(nom, passive=True)).delete()
        except Exception:
            ch = await connexion.channel()
    await connexion.close()

    print('\n' + '-' * 96)
    if echecs:
        print('===> ECHEC :')
        for e in echecs:
            print('       - ' + e)
        raise AssertionError(' | '.join(echecs))
    print('===> TOUT VERT : la garde suspend sans perdre, sans DLQ, sans doublon.')
    print('     (files et exchanges de test supprimes)')


def test_garde_ne_perd_aucun_message():
    asyncio.run(main())
