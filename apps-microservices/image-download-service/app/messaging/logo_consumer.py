import aio_pika
from typing import Optional
import json
import logging
import os
from image_download_service.core.downloader import Downloader
from common_utils.autres.DLQProperties import DLQProperties

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_TTL_MS = 30_000

# Topologie RabbitMQ -- isolee du flux FP et du flux pages images (exchanges/queues distincts)
EXCHANGE_NAME = os.environ.get("LOGO_EXCHANGE_NAME", "data_exchange_logos")
ROUTING_KEY = os.environ.get("LOGO_ROUTING_KEY", "new_data.logo")
QUEUE_NAME = os.environ.get("LOGO_QUEUE_NAME", "logo_download_tasks_queue")

# Exchanges et routing key internes (isoles pour eviter les boucles cross-service)
_INTERNAL_EXCHANGE = "logo_internal_exchange"
_INTERNAL_ROUTING_KEY = "logo.retry"
_RETRY_EXCHANGE = "logo_retry_exchange"
_RETRY_QUEUE_NAME = f"{QUEUE_NAME}_retry"
_DLQ_EXCHANGE = "logo_dlq_exchange"
_DLQ_QUEUE_NAME = f"{QUEUE_NAME}_dlq"


class LogoConsumer:
    def __init__(self, connection: aio_pika.RobustConnection):
        """
        Consumer dedie au pipeline logos fournisseur (chantier logo fournisseur, Task 2).
        Topologie RabbitMQ entierement isolee du flux FP et du flux pages images
        (PageImageConsumer). Utilise RobustConnection pour la reconnexion automatique.
        Miroir exact de PageImageConsumer (app/messaging/page_image_consumer.py).
        """
        self.connection = connection
        self.downloader = Downloader()
        self._consumer_tag: Optional[str] = None
        self._consumer_queue: Optional[aio_pika.abc.AbstractQueue] = None

        self.exchange_name = EXCHANGE_NAME
        self.routing_key = ROUTING_KEY
        self.queue_name = QUEUE_NAME
        self.internal_exchange = _INTERNAL_EXCHANGE
        self.internal_routing_key = _INTERNAL_ROUTING_KEY
        self.retry_exchange = _RETRY_EXCHANGE
        self.retry_queue_name = _RETRY_QUEUE_NAME
        self.dead_letter_exchange = _DLQ_EXCHANGE
        self.dead_letter_queue_name = _DLQ_QUEUE_NAME

        logger.info("LogoConsumer initialise (aio_pika RobustConnection).")

    async def _setup_queues(self, channel: aio_pika.abc.AbstractChannel):
        """
        Declare toutes les files d'attente et les echanges necessaires.
        Pattern miroir de PageImageConsumer._setup_queues, avec noms isoles.
        """

        # --- 1. Infrastructure pour les echecs FINALS (Dead-Letter Queue) ---
        dlx = await channel.declare_exchange(
            self.dead_letter_exchange,
            aio_pika.ExchangeType.TOPIC,
            durable=True,
        )
        dlq = await channel.declare_queue(self.dead_letter_queue_name, durable=True)
        await dlq.bind(dlx, self.internal_routing_key)

        # --- 2. Exchange interne (seul ce service y est branche, pour les retries) ---
        internal_exchange = await channel.declare_exchange(
            self.internal_exchange,
            aio_pika.ExchangeType.TOPIC,
            durable=True,
        )

        # --- 3. Infrastructure pour les tentatives (Retry Queue) ---
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
        # Bind a data_exchange_logos pour les NOUVEAUX messages depuis l'ingestion
        await main_queue.bind(exchange, self.routing_key)
        # Bind a l'exchange interne pour les RETRIES (isole, pas de contamination cross-service)
        await main_queue.bind(internal_exchange, self.internal_routing_key)

        logger.info(
            f"Queue '{self.queue_name}' declaree et bindee a '{self.exchange_name}' + '{self.internal_exchange}'."
        )
        return main_queue

    def _get_retry_count(self, message: aio_pika.abc.AbstractIncomingMessage) -> int:
        """Recupere le nombre de tentatives depuis les headers x-death (miroir PageImageConsumer)."""
        if message.headers and "x-death" in message.headers:
            for death in message.headers["x-death"]:
                if death.get("queue") == self.retry_queue_name:
                    return death.get("count", 0)
        return 0

    async def _on_message_callback(self, message: aio_pika.abc.AbstractIncomingMessage):
        """
        Callback asynchrone pour traiter un message logo fournisseur.
        Parsing direct du body (pas de wrapper BaseIngestion -- miroir PageImageConsumer).

        Semantique ACK/NACK (identique a PageImageConsumer) :
        - Succes (result dict) -> ACK
        - Erreur douce / None (erreur enregistree dans errors_logo.json) -> ACK
        - Exception non catchee -> NACK (requeue=False) -> retry via DLX
        - MAX_RETRIES depasse -> DLQ puis ACK
        """
        key = "unknown"
        domain = "unknown"
        url_logo = ""

        try:
            data = json.loads(message.body)
            key = data.get("key", "unknown")
            domain = data.get("domaine", "unknown")
            url_logo = data.get("url_logo", "")

            logger.info(
                "LogoConsumer recu key=%s domain=%s url=%s",
                key,
                domain,
                url_logo,
            )

            result = await self.downloader.process_logo_download(data)

            if result is not None:
                logger.info(
                    "LogoConsumer termine key=%s resultat=OK hosted_path=%s",
                    key,
                    result.get("hosted_path", "?"),
                )
            else:
                logger.info(
                    "LogoConsumer termine key=%s resultat=SOFT_ERROR (erreur enregistree en interne)",
                    key,
                )

            await message.ack()

        except (json.JSONDecodeError, ValueError) as e:
            logger.error(
                "LogoConsumer erreur permanente key=%s (JSON invalide) -- envoi DLQ : %s",
                key,
                e,
            )
            await self._send_to_dlq(message, e, 0)
            await message.ack()

        except Exception as e:
            retry_count = self._get_retry_count(message)
            if retry_count < MAX_RETRIES:
                logger.warning(
                    "LogoConsumer erreur transitoire key=%s (essai %d/%d) -- retry. Erreur : %s",
                    key,
                    retry_count + 1,
                    MAX_RETRIES + 1,
                    e,
                )
                await message.nack(requeue=False)  # NACK -> DLX -> retry queue
            else:
                logger.error(
                    "LogoConsumer echec apres %d tentatives key=%s -- envoi DLQ. Erreur : %s",
                    MAX_RETRIES + 1,
                    key,
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
        Publie le message dans la Dead-Letter Queue avec les metadonnees d'erreur.
        Utilise DLQProperties de common_utils (miroir PageImageConsumer).
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
                logger.info("LogoConsumer message envoye a la DLQ : %s", self.dead_letter_queue_name)
        except Exception as dlq_error:
            logger.error("LogoConsumer erreur lors de l'envoi a la DLQ : %s", dlq_error)

    async def start_consuming(self) -> None:
        """
        Declare la topologie, bind les queues, demarre la boucle de consommation.
        RobustConnection gere automatiquement les reconnexions (miroir PageImageConsumer).
        prefetch_count=1 : traitement sequentiel adapte aux telechargements longs.
        """
        channel = await self.connection.channel()

        await channel.set_qos(prefetch_count=1)

        queue = await self._setup_queues(channel)

        logger.info("LogoConsumer : en attente de messages logos fournisseur...")
        self._consumer_queue = queue
        self._consumer_tag = await queue.consume(self._on_message_callback)

    async def stop(self) -> None:
        """Annule le consumer-tag cote broker (miroir PageImageConsumer.stop)."""
        if self._consumer_tag is not None and self._consumer_queue is not None:
            try:
                await self._consumer_queue.cancel(self._consumer_tag)
            except Exception as exc:
                logger.warning("LogoConsumer stop : echec cancel consumer-tag : %s", exc)
            self._consumer_tag = None
            self._consumer_queue = None
