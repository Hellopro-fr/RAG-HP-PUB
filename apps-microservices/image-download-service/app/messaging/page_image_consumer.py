import aio_pika
import json
import logging
import os
from image_download_service.core.downloader import Downloader
from common_utils.autres.DLQProperties import DLQProperties

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_TTL_MS = 30_000

# Topologie RabbitMQ — isolée du flux FP (exchanges/queues distincts)
EXCHANGE_NAME = os.environ.get("PAGE_IMAGE_EXCHANGE_NAME", "data_exchange_pages_images")
ROUTING_KEY = os.environ.get("PAGE_IMAGE_ROUTING_KEY", "new_data.page_image")
QUEUE_NAME = os.environ.get("PAGE_IMAGE_QUEUE_NAME", "page_image_download_tasks_queue")

# Exchanges et routing key internes (isolés pour éviter les boucles cross-service)
_INTERNAL_EXCHANGE = "page_image_internal_exchange"
_INTERNAL_ROUTING_KEY = "page_image.retry"
_RETRY_EXCHANGE = "page_image_retry_exchange"
_RETRY_QUEUE_NAME = f"{QUEUE_NAME}_retry"
_DLQ_EXCHANGE = "page_image_dlq_exchange"
_DLQ_QUEUE_NAME = f"{QUEUE_NAME}_dlq"


class PageImageConsumer:
    def __init__(self, connection: aio_pika.RobustConnection):
        """
        Consumer dédié au pipeline pages images (Chantier D, spec §9.11).
        Topologie RabbitMQ entièrement isolée du flux FP (consumer.py).
        Utilise RobustConnection pour la reconnexion automatique.
        """
        self.connection = connection
        self.downloader = Downloader()
        self._consumer_tag = None

        # Noms des composants RabbitMQ (topologie isolée, miroir du pattern FP)
        self.exchange_name = EXCHANGE_NAME
        self.routing_key = ROUTING_KEY
        self.queue_name = QUEUE_NAME
        self.internal_exchange = _INTERNAL_EXCHANGE
        self.internal_routing_key = _INTERNAL_ROUTING_KEY
        self.retry_exchange = _RETRY_EXCHANGE
        self.retry_queue_name = _RETRY_QUEUE_NAME
        self.dead_letter_exchange = _DLQ_EXCHANGE
        self.dead_letter_queue_name = _DLQ_QUEUE_NAME

        logger.info("PageImageConsumer initialisé (aio_pika RobustConnection).")

    async def _setup_queues(self, channel: aio_pika.abc.AbstractChannel):
        """
        Déclare toutes les files d'attente et les échanges nécessaires.
        Pattern miroir de Consumer._setup_queues (FP), avec noms isolés.
        """

        # --- 1. Infrastructure pour les échecs FINALS (Dead-Letter Queue) ---
        dlx = await channel.declare_exchange(
            self.dead_letter_exchange,
            aio_pika.ExchangeType.TOPIC,
            durable=True,
        )
        dlq = await channel.declare_queue(self.dead_letter_queue_name, durable=True)
        await dlq.bind(dlx, self.internal_routing_key)

        # --- 2. Exchange interne (seul ce service y est bindé, pour les retries) ---
        internal_exchange = await channel.declare_exchange(
            self.internal_exchange,
            aio_pika.ExchangeType.TOPIC,
            durable=True,
        )

        # --- 3. Infrastructure pour les tentatives (Retry Queue) ---
        # La retry queue dead-letter vers l'exchange INTERNE (pas data_exchange_pages_images)
        # pour que les messages réessayés ne soient pas vus par d'autres services.
        retry_exchange = await channel.declare_exchange(
            self.retry_exchange,
            aio_pika.ExchangeType.TOPIC,
            durable=True,
        )
        retry_queue = await channel.declare_queue(
            self.retry_queue_name,
            durable=True,
            arguments={
                "x-message-ttl": RETRY_TTL_MS,
                "x-dead-letter-exchange": self.internal_exchange,
                "x-dead-letter-routing-key": self.internal_routing_key,
            },
        )
        await retry_queue.bind(retry_exchange, self.internal_routing_key)

        # --- 4. Configuration de la Queue Principale ---
        exchange = await channel.declare_exchange(
            self.exchange_name,
            aio_pika.ExchangeType.TOPIC,
            durable=True,
        )
        main_queue = await channel.declare_queue(
            self.queue_name,
            durable=True,
            arguments={
                "x-dead-letter-exchange": self.retry_exchange,
                "x-dead-letter-routing-key": self.internal_routing_key,
            },
        )
        # Bind à data_exchange_pages_images pour les NOUVEAUX messages depuis l'ingestion
        await main_queue.bind(exchange, self.routing_key)
        # Bind à l'exchange interne pour les RETRIES (isolé, pas de contamination cross-service)
        await main_queue.bind(internal_exchange, self.internal_routing_key)

        logger.info(
            f"Queue '{self.queue_name}' déclarée et bindée à '{self.exchange_name}' + '{self.internal_exchange}'."
        )
        return main_queue

    def _get_retry_count(self, message: aio_pika.abc.AbstractIncomingMessage) -> int:
        """Récupère le nombre de tentatives depuis les headers x-death (miroir FP)."""
        # Note : RabbitMQ consolide les entrées x-death par (queue, reason). On lit donc
        # une seule entrée pour notre retry queue et son `count` est incrémenté à chaque
        # rejet successif depuis cette queue. Pas besoin de sommer plusieurs entrées.
        if message.headers and "x-death" in message.headers:
            for death in message.headers["x-death"]:
                if death.get("queue") == self.retry_queue_name:
                    return death.get("count", 0)
        return 0

    async def _on_message_callback(self, message: aio_pika.abc.AbstractIncomingMessage):
        """
        Callback asynchrone pour traiter un message pages images.
        Parsing direct du body (pas de wrapper BaseIngestion — différent du flux FP).

        Sémantique ACK/NACK (miroir FP) :
        - Succès (result dict) → ACK
        - Erreur douce / None (erreur enregistrée dans errors_pages.json) → ACK
          (process_page_image gère déjà l'erreur en interne)
        - Exception non catchée → NACK (requeue=False) → retry via DLX
        - MAX_RETRIES dépassé → DLQ puis ACK
        """
        id_image_isi = "unknown"
        domain = "unknown"
        url_image = ""

        try:
            data = json.loads(message.body)
            id_image_isi = data.get("id_image_isi", "unknown")
            domain = data.get("domaine", "unknown")
            url_image = data.get("url_image", "")

            logger.info(
                "PageImageConsumer reçu id_image_isi=%s domain=%s url=%s",
                id_image_isi,
                domain,
                url_image,
            )

            result = await self.downloader.process_page_image(data)

            # result est l'entrée manifest en cas de succès, ou None si erreur douce
            # (l'erreur est déjà enregistrée dans errors_pages.json par process_page_image)
            if result is not None:
                logger.info(
                    "PageImageConsumer terminé id_image_isi=%s résultat=OK filename=%s",
                    id_image_isi,
                    result.get("filename", "?"),
                )
            else:
                logger.info(
                    "PageImageConsumer terminé id_image_isi=%s résultat=SOFT_ERROR (erreur enregistrée en interne)",
                    id_image_isi,
                )

            await message.ack()

        except (json.JSONDecodeError, ValueError) as e:
            # Erreur permanente : message invalide → DLQ directement (pas de retry)
            logger.error(
                "PageImageConsumer erreur permanente id_image_isi=%s (JSON invalide) — envoi DLQ : %s",
                id_image_isi,
                e,
            )
            await self._send_to_dlq(message, e, 0)
            await message.ack()

        except Exception as e:
            # Erreur potentiellement transitoire → retry ou DLQ selon le compteur
            retry_count = self._get_retry_count(message)
            if retry_count < MAX_RETRIES:
                logger.warning(
                    "PageImageConsumer erreur transitoire id_image_isi=%s (essai %d/%d) — retry. Erreur : %s",
                    id_image_isi,
                    retry_count + 1,
                    MAX_RETRIES + 1,
                    e,
                )
                await message.nack(requeue=False)  # NACK → DLX → retry queue
            else:
                logger.error(
                    "PageImageConsumer échec après %d tentatives id_image_isi=%s — envoi DLQ. Erreur : %s",
                    MAX_RETRIES + 1,
                    id_image_isi,
                    e,
                )
                await self._send_to_dlq(message, e, MAX_RETRIES)
                await message.ack()

    async def _send_to_dlq(
        self,
        message: aio_pika.abc.AbstractIncomingMessage,
        error: Exception,
        retry_count: int,
    ) -> None:
        """
        Publie le message dans la Dead-Letter Queue avec les métadonnées d'erreur.
        Utilise DLQProperties de common_utils (miroir FP).
        """
        try:
            async with self.connection.channel() as channel:
                dlx = await channel.get_exchange(self.dead_letter_exchange, ensure=True)

                dlq_headers = DLQProperties.create_dlq_headers(
                    error,
                    "image-download-service",
                    retry_count,
                    message,
                )

                await dlx.publish(
                    aio_pika.Message(
                        body=message.body,
                        headers=dlq_headers,
                        delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                    ),
                    routing_key=self.internal_routing_key,
                )
                logger.info("PageImageConsumer message envoyé à la DLQ : %s", self.dead_letter_queue_name)
        except Exception as dlq_error:
            # TODO Chantier D follow-up : si _send_to_dlq échoue, le message est ack() côté caller
            #                              → perte silencieuse. Hérité du pattern FP (consumer.py).
            #                              Fix structurel à coordonner avec FP (NACK requeue ou
            #                              retry-publish vers DLQ avec circuit-breaker).
            logger.error("PageImageConsumer erreur lors de l'envoi à la DLQ : %s", dlq_error)

    async def start_consuming(self) -> None:
        """
        Déclare la topologie, bind les queues, démarre la boucle de consommation.
        RobustConnection gère automatiquement les reconnexions (miroir FP).
        prefetch_count=1 : traitement séquentiel adapté aux téléchargements longs.
        """
        channel = await self.connection.channel()

        # Traiter 1 message à la fois (téléchargements potentiellement longs)
        await channel.set_qos(prefetch_count=1)

        queue = await self._setup_queues(channel)

        logger.info("PageImageConsumer : en attente de messages pages images...")
        self._consumer_tag = await queue.consume(self._on_message_callback)

    async def stop(self) -> None:
        """Annule le consumer-tag côté broker. À appeler dans le lifespan shutdown
        avant `task.cancel()` pour éviter qu'aio_pika ne laisse une inscription orpheline.
        """
        if self._consumer_tag is not None:
            try:
                await self._consumer_tag.cancel()
            except Exception as exc:
                logger.warning("PageImageConsumer stop : échec cancel consumer-tag : %s", exc)
            self._consumer_tag = None
