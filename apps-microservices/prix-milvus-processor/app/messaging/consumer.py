import pika
import json
import time
import logging

from app.core.processor import insertion_data

EXCHANGE_NAME = "prix_produits_embedded_data_exchange"
ROUTING_KEY = "data.prix_produits.ready_for_insertion"
QUEUE_NAME = "insertion_prix_produits_queue"

RETRY_EXCHANGE = "prix_produits_retry_exchange"
RETRY_QUEUE = "insertion_prix_produits_retry_queue"
RETRY_TTL = 30000  # 30 secondes

DLQ_EXCHANGE = "prix_produits_dlq_exchange"
DLQ_QUEUE = "insertion_prix_produits_dlq_queue"

MAX_RETRIES = 3


class Consumer:
    def __init__(self, connection, publisher):
        self.connection = connection
        self.channel = connection.channel()
        self.publisher = publisher

        self.channel.basic_qos(prefetch_count=1)

        # --- Main exchange & queue ---
        self.channel.exchange_declare(
            exchange=EXCHANGE_NAME, exchange_type="topic", durable=True
        )
        self.channel.queue_declare(queue=QUEUE_NAME, durable=True)
        self.channel.queue_bind(
            exchange=EXCHANGE_NAME, queue=QUEUE_NAME, routing_key=ROUTING_KEY
        )

        # --- Retry exchange & queue ---
        self.channel.exchange_declare(
            exchange=RETRY_EXCHANGE, exchange_type="direct", durable=True
        )
        self.channel.queue_declare(
            queue=RETRY_QUEUE,
            durable=True,
            arguments={
                "x-dead-letter-exchange": EXCHANGE_NAME,
                "x-dead-letter-routing-key": ROUTING_KEY,
                "x-message-ttl": RETRY_TTL,
            },
        )
        self.channel.queue_bind(
            exchange=RETRY_EXCHANGE, queue=RETRY_QUEUE, routing_key="retry"
        )

        # --- DLQ exchange & queue ---
        self.channel.exchange_declare(
            exchange=DLQ_EXCHANGE, exchange_type="direct", durable=True
        )
        self.channel.queue_declare(queue=DLQ_QUEUE, durable=True)
        self.channel.queue_bind(
            exchange=DLQ_EXCHANGE, queue=DLQ_QUEUE, routing_key="dlq"
        )

        logging.info(
            f"[Consumer] Exchanges et queues configurés : {EXCHANGE_NAME} → {QUEUE_NAME}"
        )

    def _on_message_callback(self, ch, method, properties, body):
        retry_count = 0
        if properties.headers and "x-retry-count" in properties.headers:
            retry_count = properties.headers["x-retry-count"]

        try:
            data = json.loads(body)
            logging.info(
                f"[Consumer] Message reçu (retry={retry_count}): id_produit={data.get('data', [{}])[0].get('id_produit', '?') if data.get('data') else '?'}"
            )

            result = insertion_data(data)

            # Publier le résultat
            if result and self.publisher:
                self.publisher.publish(result)

            ch.basic_ack(delivery_tag=method.delivery_tag)
            logging.info("[Consumer] ✓ Message traité avec succès.")

        except json.JSONDecodeError as e:
            logging.error(
                f"[Consumer] Message non parsable (JSON invalide) → DLQ : {e}"
            )
            self._send_to_dlq(ch, method, body, str(e))

        except Exception as e:
            logging.error(
                f"[Consumer] Erreur traitement (retry={retry_count}/{MAX_RETRIES}): {e}"
            )

            if retry_count < MAX_RETRIES:
                self._send_to_retry(ch, method, body, retry_count)
            else:
                logging.error(f"[Consumer] Max retries atteint → DLQ")
                self._send_to_dlq(ch, method, body, str(e))

    def _send_to_retry(self, ch, method, body, retry_count):
        try:
            headers = {"x-retry-count": retry_count + 1}
            self.channel.basic_publish(
                exchange=RETRY_EXCHANGE,
                routing_key="retry",
                body=body,
                properties=pika.BasicProperties(delivery_mode=2, headers=headers),
            )
            ch.basic_ack(delivery_tag=method.delivery_tag)
            logging.info(
                f"[Consumer] Message envoyé en retry (tentative {retry_count + 1}/{MAX_RETRIES})"
            )
        except Exception as e:
            logging.error(f"[Consumer] Erreur envoi retry : {e}")
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

    def _send_to_dlq(self, ch, method, body, error_message):
        try:
            headers = {
                "x-error": error_message,
                "x-original-exchange": EXCHANGE_NAME,
                "x-original-routing-key": ROUTING_KEY,
                "x-original-queue": QUEUE_NAME,
                "x-timestamp": str(time.time()),
            }
            self.channel.basic_publish(
                exchange=DLQ_EXCHANGE,
                routing_key="dlq",
                body=body,
                properties=pika.BasicProperties(delivery_mode=2, headers=headers),
            )
            ch.basic_ack(delivery_tag=method.delivery_tag)
            logging.info("[Consumer] Message envoyé en DLQ.")
        except Exception as e:
            logging.error(f"[Consumer] Erreur envoi DLQ : {e}")
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

    def start_consuming(self):
        self.channel.basic_consume(
            queue=QUEUE_NAME,
            on_message_callback=self._on_message_callback,
            auto_ack=False,
        )
        logging.info(f"[Consumer] 🎧 En attente de messages sur '{QUEUE_NAME}'...")
        self.channel.start_consuming()
