# -*- coding: utf-8 -*-
"""Preuve du design de garde pour les consumers a CALLBACK (template-llm, nettoyage-ocr).

Ces deux services ne piochent pas dans leur file : ils s'y ABONNENT. Le callback ne fait
que deposer le message dans un tampon interne, et un batch_processor separe traite par lots
et acquitte a la fin. La garde ne peut donc pas etre la meme que celle des consumers a
iterateur : ici on annule l'abonnement, on laisse le tampon se vider, on se reabonne apres.

Ce fichier prouve les 4 points que la lecture du source d'aio_pika ne pouvait qu'indiquer :

  1. un `cancel` ne perd aucun message et n'en envoie aucun en DLQ ;
  2. le tampon deja rempli se vide en SECONDES (pas en heures) -- donc le consumer_timeout
     du broker (30 min par defaut sur ces files, qui ne declarent pas x-consumer-timeout)
     n'est jamais en jeu ;
  3. le reabonnement relance vraiment le flux, sans doublon ni perte ;
  4. une COUPURE RESEAU pendant la fenetre chere ne reabonne pas le consumer -- c'est le
     piege que `RobustQueue` pourrait tendre, puisqu'il restaure ses consumers apres
     reconnexion. Le source dit que `cancel()` fait `self._consumers.pop(tag, None)` ;
     ici on le VERIFIE.

GARDE-FOU : le test ECHOUE s'il n'a rien exerce. Vecu le 18-08-2026 sur le test frere --
le traitement etait instantane, la file se vidait avant la bascule, et le test affichait
vert sans avoir jamais rien suspendu.

SAUTE par defaut. Pour l'executer, fournir un broker jetable :

    RABBITMQ_URL_TEST=amqp://guest:guest@localhost:5672/ pytest tests/ -k integration -s
"""
import asyncio
import os
import subprocess
import sys
import time

import pytest

URL = os.environ.get('RABBITMQ_URL_TEST')

pytestmark = pytest.mark.skipif(
    not URL,
    reason="definir RABBITMQ_URL_TEST pour lancer ce test (broker jetable requis)",
)

aio_pika = pytest.importorskip('aio_pika')

PREFIXE = 'test_garde_callback'
QUEUE = PREFIXE + '_queue'
QUEUE_RETRY = QUEUE + '_retry'
QUEUE_DLQ = QUEUE + '_dlq'
EXCHANGE = PREFIXE + '_exchange'
EXCHANGE_RETRY = PREFIXE + '_retry_exchange'
EXCHANGE_DLQ = PREFIXE + '_dlq_exchange'
ROUTING = 'test.callback.ready'

# --- constantes copiees des services reels ---
RETRY_TTL_MS = 30000        # template-llm:24, nettoyage:17
BATCH_SIZE = 16             # template-llm:17  (nettoyage a 1)
BATCH_TIMEOUT_S = 2.0       # template-llm:22
PREFETCH = BATCH_SIZE       # template-llm:192 -> set_qos(prefetch_count=BATCH_SIZE)

# --- parametres du scenario ---
NB_MESSAGES = 40
DUREE_TRAITEMENT_S = 0.35   # simule l'appel LLM ; sans ca le test ne prouve rien
TICK_GARDE_S = 0.2          # sleep(60) en production
BASCULE_APRES = 4


class ConsumerSousTest:
    """Structure IDENTIQUE a template-llm-service / nettoyage-bruit-ocr-service.

    _on_message ne fait que remplir le tampon ; batch_processor traite par lots et
    acquitte APRES. La seule chose ajoutee est la boucle de garde de start_consuming().
    """

    def __init__(self, connection, predicat):
        self.connection = connection
        self.est_heure_pleine = predicat
        self.message_buffer = asyncio.Queue()
        self.queue = None
        self.tag = None
        # observabilite pour les assertions
        self.traites = []
        self.nb_cancel = 0
        self.nb_consume = 0
        self.erreurs_garde = []
        self.instant_dernier_ack = None

    async def _on_message(self, message):
        await self.message_buffer.put(message)

    async def batch_processor(self):
        while True:
            batch = []
            try:
                batch.append(await self.message_buffer.get())
                while len(batch) < BATCH_SIZE:
                    try:
                        batch.append(await asyncio.wait_for(
                            self.message_buffer.get(), timeout=BATCH_TIMEOUT_S))
                    except asyncio.TimeoutError:
                        break
            except asyncio.CancelledError:
                return

            await asyncio.sleep(DUREE_TRAITEMENT_S)          # l'appel LLM
            for msg in batch:
                try:
                    await msg.ack()
                    self.traites.append(msg.body.decode())
                    self.instant_dernier_ack = time.monotonic()
                except Exception as e:                        # canal ferme -> requeue broker
                    self.erreurs_garde.append('ack: %s' % type(e).__name__)

    async def garde(self):
        """LA BOUCLE A PROUVER -- celle qui remplacera `await queue.consume(...)`.

        CORRECTION du 20-08 apres echec du test : les erreurs de CANAL et de CONNEXION
        doivent REMONTER, pas etre avalees. Premiere version, elle attrapait tout et
        retentait : apres une coupure, `self.queue` restait attachee au canal mort et la
        boucle retentait a l'infini sur un canal qui ne revenait jamais -- service muet,
        rien en DLQ, aucune alerte. Or main.py:48 attrape deja
        (AMQPConnectionError, ChannelInvalidStateError) et reconstruit connexion +
        consumer : il suffit de le laisser faire son travail.

        C'est pourquoi cette boucle doit etre AWAITEE dans start_consuming(), et non
        lancee en create_task() -- sinon l'exception mourrait dans une tache orpheline.
        """
        while True:
            if self.est_heure_pleine():
                if self.tag is not None:
                    await self.queue.cancel(self.tag)
                    self.tag = None
                    self.nb_cancel += 1
            elif self.tag is None:
                self.tag = await self.queue.consume(self._on_message)
                self.nb_consume += 1
            await asyncio.sleep(TICK_GARDE_S)


async def declarer(channel):
    """Topologie de template-llm-service : DLX/DLK, retry TTL 30 s, et PAS de
    x-consumer-timeout sur la file principale (consumer.py:64-71)."""
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
                   'x-dead-letter-routing-key': ROUTING})
    await q.bind(ex, routing_key=ROUTING)
    return ex, q, q_dlq


async def profondeur(connexion, nom):
    ch = await connexion.channel()
    try:
        q = await ch.declare_queue(nom, passive=True)
        return q.declaration_result.message_count
    finally:
        await ch.close()


async def nettoyer(connexion):
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


async def main():
    echecs = []
    etat = {'pleine': False}

    print('=' * 90)
    print("PREUVE DE LA GARDE 'CALLBACK' contre un VRAI RabbitMQ")
    print('  broker   :', URL.replace('guest:guest', 'guest:***'))
    print('  aio_pika :', aio_pika.__version__)
    print('=' * 90)

    connexion = await aio_pika.connect_robust(URL)
    channel = await connexion.channel()
    await channel.set_qos(prefetch_count=PREFETCH)

    # table rase
    for nom in (QUEUE, QUEUE_RETRY, QUEUE_DLQ):
        try:
            await (await channel.declare_queue(nom, passive=True)).purge()
        except Exception:
            channel = await connexion.channel()
            await channel.set_qos(prefetch_count=PREFETCH)

    exchange, queue, _ = await declarer(channel)

    for i in range(1, NB_MESSAGES + 1):
        await exchange.publish(
            aio_pika.Message(body=('m%d' % i).encode(),
                             delivery_mode=aio_pika.DeliveryMode.PERSISTENT),
            routing_key=ROUTING)
    print('\n%d messages publies (prefetch=%d, traitement=%.2fs/lot)'
          % (NB_MESSAGES, PREFETCH, DUREE_TRAITEMENT_S))

    consumer = ConsumerSousTest(connexion, lambda: etat['pleine'])
    consumer.queue = queue
    t_batch = asyncio.create_task(consumer.batch_processor())
    t_garde = asyncio.create_task(consumer.garde())

    # ---------- phase 1 : heures creuses, le flux tourne ----------
    for _ in range(200):
        if len(consumer.traites) >= BASCULE_APRES:
            break
        await asyncio.sleep(0.05)
    traites_avant = len(consumer.traites)
    print('\n--- phase 1 : heures creuses ---')
    print('  traites .......................... %d' % traites_avant)
    print('  abonnements (consume) ............ %d' % consumer.nb_consume)
    if traites_avant == 0:
        echecs.append("phase 1 : rien n'a ete traite en heures creuses")

    # ---------- phase 2 : BASCULE en heure pleine ----------
    etat['pleine'] = True
    t_bascule = time.monotonic()
    await asyncio.sleep(TICK_GARDE_S * 3)          # laisse la garde faire son cancel

    cancels = consumer.nb_cancel
    en_file_pendant = await profondeur(connexion, QUEUE)
    dlq_pendant = await profondeur(connexion, QUEUE_DLQ)
    retry_pendant = await profondeur(connexion, QUEUE_RETRY)

    # le tampon doit se vider tout seul : on mesure combien de temps ca prend
    await asyncio.sleep(DUREE_TRAITEMENT_S * 3 + BATCH_TIMEOUT_S + 0.5)
    delai_vidage = (consumer.instant_dernier_ack - t_bascule) if consumer.instant_dernier_ack else -1
    traites_apres_vidage = len(consumer.traites)

    # rien ne doit plus bouger ensuite
    await asyncio.sleep(1.5)
    fige = len(consumer.traites) == traites_apres_vidage

    print('\n--- phase 2 : fenetre CHERE ---')
    print('  cancel appele .................... %d   %s' % (
        cancels, 'OK' if cancels == 1 else 'ECHEC (attendu 1)'))
    print('  messages READY pendant la fenetre  %d   %s' % (
        en_file_pendant,
        'OK (la suspension a ete exercee)' if en_file_pendant else 'NON CONCLUANT'))
    print('  en DLQ ........................... %d   %s' % (
        dlq_pendant, 'OK' if dlq_pendant == 0 else 'ECHEC'))
    print('  en RETRY ......................... %d   %s' % (
        retry_pendant, 'OK' if retry_pendant == 0 else 'ECHEC'))
    print('  tampon vide en ................... %.2f s  %s' % (
        delai_vidage, 'OK (secondes, pas heures)' if 0 <= delai_vidage < 30 else 'A VERIFIER'))
    print('  flux fige apres vidage ........... %s' % ('OUI (OK)' if fige else 'NON -- ECHEC'))
    print('  traites au total ................. %d' % traites_apres_vidage)

    if cancels != 1:
        echecs.append('cancel appele %d fois au lieu de 1 (la garde boucle ?)' % cancels)
    if en_file_pendant == 0:
        echecs.append("TEST NON CONCLUANT : aucun message n'attendait pendant la fenetre "
                      "(augmenter NB_MESSAGES ou DUREE_TRAITEMENT_S)")
    if dlq_pendant:
        echecs.append('%d message(s) en DLQ pendant la fenetre' % dlq_pendant)
    if retry_pendant:
        echecs.append('%d message(s) parti(s) en retry' % retry_pendant)
    if not fige:
        echecs.append('des messages ont ete traites APRES le vidage du tampon, en heure pleine')
    if delai_vidage < 0 or delai_vidage > 30:
        echecs.append('le tampon ne se vide pas en quelques secondes (%.1fs)' % delai_vidage)

    perdus = NB_MESSAGES - traites_apres_vidage - en_file_pendant
    print('  conservation ..................... %d publies = %d traites + %d en file  %s' % (
        NB_MESSAGES, traites_apres_vidage, en_file_pendant,
        '(ecart %d, tolere : messages en vol au moment du comptage)' % perdus if perdus else '(OK)'))

    # ---------- phase 3 : VRAIE coupure reseau pendant la fenetre chere ----------
    # Le point que seule une execution peut trancher : RobustQueue RESTAURE ses consumers
    # apres reconnexion. Si cancel() ne les avait pas retires de `_consumers`, le service
    # se reabonnerait ICI, en pleine fenetre chere, sans que rien ne le signale.
    #
    # On coupe cote BROKER (pas un channel.close() cote client, qui est volontaire et
    # definitif) : c'est ce qui declenche vraiment la machinerie de restauration.
    traites_avant_coupure = len(consumer.traites)
    coupure_faite = False
    try:
        r = subprocess.run(['wsl', '-u', 'root', '-e', 'bash', '-lc',
                            'rabbitmqctl close_all_connections "test garde" 2>&1 | tail -2'],
                           capture_output=True, text=True, timeout=60)
        coupure_faite = r.returncode == 0
        print('\n--- phase 3 : VRAIE coupure (broker) PENDANT la fenetre chere ---')
        print('  rabbitmqctl ...................... %s' % (r.stdout.strip()[:70] or 'ok'))
    except Exception as e:
        print('\n--- phase 3 : coupure broker INDISPONIBLE (%s) ---' % type(e).__name__)

    if coupure_faite:
        await asyncio.sleep(6.0)          # laisse RobustConnection reconnecter
        traites_apres_coupure = len(consumer.traites)
        reabonne_a_tort = traites_apres_coupure > traites_avant_coupure
        print('  traites avant / apres ............ %d / %d' % (
            traites_avant_coupure, traites_apres_coupure))
        print('  reabonnement a tort .............. %s' % (
            'OUI -- ECHEC GRAVE' if reabonne_a_tort else 'NON (OK)'))
        print('  garde encore vivante ............. %s' % (
            'NON' if t_garde.done() else 'OUI'))
        if reabonne_a_tort:
            echecs.append('la reconnexion a REABONNE le consumer en pleine fenetre chere '
                          '(%d messages consommes)' % (traites_apres_coupure - traites_avant_coupure))
        # si la garde est morte, c'est que l'erreur remonte -- comportement VOULU, mais
        # alors c'est main.py qui reconstruit : on le note et on relance une garde neuve
        if t_garde.done():
            exc = t_garde.exception()
            print('  erreur remontee .................. %s (main.py la traite)' %
                  (type(exc).__name__ if exc else 'aucune'))
            consumer.tag = None
            channel = await connexion.channel()
            await channel.set_qos(prefetch_count=PREFETCH)
            _, queue, _ = await declarer(channel)
            consumer.queue = queue
            t_garde = asyncio.create_task(consumer.garde())
    else:
        print('  (sous-phase sautee : pas de rabbitmqctl joignable)')

    # ---------- phase 4 : retour en heures creuses ----------
    etat['pleine'] = False
    for _ in range(400):
        if len(consumer.traites) >= NB_MESSAGES:
            break
        if t_garde.done() and t_garde.exception():
            break
        await asyncio.sleep(0.1)

    reste = await profondeur(connexion, QUEUE)
    dlq_fin = await profondeur(connexion, QUEUE_DLQ)
    doublons = len(consumer.traites) != len(set(consumer.traites))
    manquants = sorted(set('m%d' % i for i in range(1, NB_MESSAGES + 1)) - set(consumer.traites),
                       key=lambda s: int(s[1:]))

    print('\n--- phase 4 : retour en heures creuses ---')
    print('  reabonnements (consume) .......... %d   %s' % (
        consumer.nb_consume, 'OK (>=2 : il a bien repris)' if consumer.nb_consume >= 2 else 'ECHEC'))
    print('  total traites .................... %d / %d %s' % (
        len(consumer.traites), NB_MESSAGES,
        '(OK)' if len(consumer.traites) == NB_MESSAGES else '(INCOMPLET)'))
    print('  doublons ......................... %s' % ('AUCUN (OK)' if not doublons else 'OUI -- ECHEC'))
    print('  reste en file .................... %d' % reste)
    print('  DLQ finale ....................... %d' % dlq_fin)
    if manquants:
        print('  MANQUANTS ........................ %s' % manquants[:10])
        echecs.append('messages jamais traites : %s' % manquants[:10])
    if consumer.nb_consume < 2:
        echecs.append("le consumer ne s'est pas reabonne apres la fenetre")
    if doublons:
        echecs.append('messages traites en double')
    if dlq_fin:
        echecs.append('%d message(s) en DLQ a la fin' % dlq_fin)
    if consumer.erreurs_garde:
        print('  erreurs rencontrees .............. %s' % consumer.erreurs_garde[:6])

    # ---------- phase 5 : un canal MORT doit faire REMONTER l'erreur ----------
    # C'est la correction issue du premier echec. Une garde qui avale les erreurs de canal
    # retente eternellement sur un canal qui ne revient jamais : service muet, rien en DLQ,
    # aucune alerte. Le comportement voulu est que l'exception remonte, parce que
    # main.py:48 attrape (AMQPConnectionError, ChannelInvalidStateError) et reconstruit
    # connexion + consumer. On verifie ici que la garde ne l'etouffe PAS.
    print('\n--- phase 5 : canal tue -> la garde doit LEVER, pas boucler en silence ---')
    etat['pleine'] = False
    consumer.tag = None                       # force un consume() au prochain tour
    try:
        await consumer.queue.channel.close()
    except Exception:
        pass
    for _ in range(60):
        if t_garde.done():
            break
        await asyncio.sleep(0.1)

    if not t_garde.done():
        print('  la garde tourne encore .......... ECHEC (elle avale l\'erreur)')
        echecs.append("la garde n'a pas leve sur un canal mort : elle boucle en silence, "
                      "main.py ne peut pas reconstruire")
    else:
        exc = t_garde.exception()
        nom = type(exc).__name__ if exc else 'aucune'
        traite = exc is not None and (
            'ChannelInvalidState' in nom or 'AMQPConnection' in nom
            or 'ChannelClosed' in nom or 'Connection' in nom)
        print('  exception levee ................. %s' % nom)
        print('  reconnaissable par main.py ...... %s' % (
            'OUI (OK)' if traite else 'NON -- a verifier'))
        if exc is None:
            echecs.append('la garde est sortie sans exception sur un canal mort')
        elif not traite:
            echecs.append("la garde leve %s, que main.py:48 n'attrape pas -> "
                          "le conteneur tomberait sans reconnexion" % nom)

    # ---------- fin ----------
    t_garde.cancel()
    t_batch.cancel()
    for t in (t_garde, t_batch):
        try:
            await t
        except (asyncio.CancelledError, Exception):
            pass
    try:
        await nettoyer(connexion)
    except Exception as e:
        print('  (nettoyage partiel : %s)' % type(e).__name__)
    await connexion.close()

    print('\n' + '-' * 90)
    if echecs:
        print('===> ECHEC :')
        for e in echecs:
            print('       - ' + e)
        pytest.fail('garde callback : ' + ' | '.join(echecs))
    print('===> TOUT VERT : la garde par annulation/reabonnement ne perd rien, ne jette rien,')
    print('     ne duplique rien, vide son tampon en quelques secondes, et ne se reabonne pas')
    print('     apres une coupure reseau survenue en pleine fenetre chere.')


def test_garde_callback_contre_vrai_broker():
    """Point d'entree pytest : rejoue le scenario complet contre le broker fourni."""
    asyncio.run(main())


if __name__ == '__main__':
    asyncio.run(main())
