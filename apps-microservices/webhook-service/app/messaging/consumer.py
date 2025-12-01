import pika
import json
import logging
from webhook_service.core.processor import send_webhook

# Configuration du logging structuré
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class Consumer:
    def __init__(self, connection: pika.BlockingConnection):
        """
        Initialise le consumer pour le webhook-service.

        Args:
            connection: Connexion RabbitMQ déjà établie
        """
        self.connection = connection
        self.channel = self.connection.channel()
        self.exchange_name = 'inserted_data_exchange'
        self.routing_key = 'data.ready_for_webhook'
        self.queue_name = 'webhook_queue'

        # Déclaration des ressources RabbitMQ
        self._declare_resources()

        logger.info("✅ Consumer webhook-service initialisé avec succès")

    def _declare_resources(self):
        """
        Déclare l'exchange, la queue et le binding RabbitMQ.
        """
        try:
            # Déclaration de l'exchange
            self.channel.exchange_declare(
                exchange=self.exchange_name,
                exchange_type='topic',
                durable=True
            )
            logger.info(f"Exchange '{self.exchange_name}' déclaré")

            # Déclaration de la queue
            self.channel.queue_declare(
                queue=self.queue_name,
                durable=True
            )
            logger.info(f"Queue '{self.queue_name}' déclarée")

            # Binding queue -> exchange
            self.channel.queue_bind(
                exchange=self.exchange_name,
                queue=self.queue_name,
                routing_key=self.routing_key
            )
            logger.info(
                f"Binding créé: queue '{self.queue_name}' → "
                f"exchange '{self.exchange_name}' (routing_key: '{self.routing_key}')"
            )

        except pika.exceptions.AMQPError as e:
            logger.error(f"❌ Erreur lors de la déclaration des ressources RabbitMQ: {e}")
            raise

    def _on_message_callback(self, ch, method, properties, body):
        """
        Callback appelé lors de la réception d'un message.

        Args:
            ch: Channel
            method: Méthode de livraison
            properties: Propriétés du message
            body: Corps du message (bytes)
        """
        try:
            # Décodage du message JSON
            data = json.loads(body)
            logger.info(f"📥 Message reçu pour collection: {data.get('collection', 'unknown')}")

            # Appel de la logique métier
            success = send_webhook(data)

            if success:
                # Acquittement du message en cas de succès
                ch.basic_ack(delivery_tag=method.delivery_tag)
                logger.info(f"✅ Message traité et acquitté (delivery_tag: {method.delivery_tag})")
            else:
                # NACK sans requeue en cas d'échec (après tous les retries)
                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
                logger.warning(
                    f"⚠️ Message rejeté après échec de traitement "
                    f"(delivery_tag: {method.delivery_tag}, requeue=False)"
                )
                # TODO: Le message devrait être envoyé vers une Dead Letter Queue

        except json.JSONDecodeError as e:
            logger.error(f"❌ Erreur de décodage JSON du message: {e}")
            # Rejeter le message malformé sans requeue
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

        except Exception as e:
            logger.exception(f"❌ Erreur inattendue lors du traitement du message: {e}")
            # Rejeter le message avec requeue pour retry
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)

    def start_consuming(self):
        """
        Démarre la boucle d'écoute des messages avec gestion de reconnexion.
        """
        max_reconnect_attempts = 3
        reconnect_delay = 5

        for attempt in range(max_reconnect_attempts):
            try:
                # Configuration du consumer
                self.channel.basic_consume(
                    queue=self.queue_name,
                    on_message_callback=self._on_message_callback
                )

                logger.info(f"👂 webhook-service en attente de messages sur queue '{self.queue_name}'...")
                self.channel.start_consuming()

                # Si on arrive ici, la consommation s'est arrêtée proprement
                break

            except (pika.exceptions.AMQPConnectionError, pika.exceptions.ChannelClosedByBroker) as e:
                logger.error(
                    f"⚠️ Connexion RabbitMQ perdue (tentative {attempt + 1}/{max_reconnect_attempts}): {e}"
                )

                if attempt < max_reconnect_attempts - 1:
                    logger.info(f"⏳ Tentative de reconnexion dans {reconnect_delay}s...")
                    import time
                    time.sleep(reconnect_delay)

                    try:
                        # Recréer le channel et redéclarer les ressources
                        self.channel = self.connection.channel()
                        self._declare_resources()
                        logger.info("✅ Reconnexion réussie")
                    except Exception as reconnect_error:
                        logger.error(f"❌ Échec de la reconnexion: {reconnect_error}")
                else:
                    logger.critical(
                        f"❌ Échec de reconnexion après {max_reconnect_attempts} tentatives. "
                        "Arrêt du consumer."
                    )
                    raise

            except KeyboardInterrupt:
                logger.info("🛑 Arrêt demandé par l'utilisateur (KeyboardInterrupt)")
                self.stop_consuming()
                break

            except Exception as e:
                logger.exception(f"❌ Erreur critique dans le consumer: {e}")
                raise

    def stop_consuming(self):
        """
        Arrête proprement la consommation de messages.
        """
        try:
            if self.channel and self.channel.is_open:
                logger.info("🛑 Arrêt de la consommation des messages...")
                self.channel.stop_consuming()
                logger.info("✅ Consumer arrêté proprement")
        except Exception as e:
            logger.error(f"⚠️ Erreur lors de l'arrêt du consumer: {e}")
