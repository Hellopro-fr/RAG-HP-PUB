import pika
import json
import logging

PUBLISH_EXCHANGE = "inserted_data_exchange"
PUBLISH_ROUTING_KEY = "data.ready_for_webhook"


class Publisher:
    def __init__(self, connection):
        self.connection = connection
        self.channel = connection.channel()
        self.channel.exchange_declare(
            exchange=PUBLISH_EXCHANGE, exchange_type="topic", durable=True
        )
        logging.info(f"[Publisher] Exchange '{PUBLISH_EXCHANGE}' déclaré.")

    def publish(self, message: dict):
        try:
            if not self.connection or self.connection.is_closed:
                logging.warning(
                    "[Publisher] Connexion fermée, tentative de reconnexion..."
                )
                self.connection = pika.BlockingConnection(
                    pika.URLParameters(self.connection)
                )
                self.channel = self.connection.channel()
                self.channel.exchange_declare(
                    exchange=PUBLISH_EXCHANGE, exchange_type="topic", durable=True
                )

            body = json.dumps(message)
            self.channel.basic_publish(
                exchange=PUBLISH_EXCHANGE,
                routing_key=PUBLISH_ROUTING_KEY,
                body=body,
                properties=pika.BasicProperties(delivery_mode=2),  # persistent
            )
            logging.info(
                f"[Publisher] ✓ Message publié sur '{PUBLISH_EXCHANGE}' avec clé '{PUBLISH_ROUTING_KEY}'"
            )
        except Exception as e:
            logging.error(f"[Publisher] Erreur publication : {e}")
