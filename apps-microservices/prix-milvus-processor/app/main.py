import os
import pika
import logging

from prometheus_client import start_http_server

from app.messaging.publisher import Publisher
from app.messaging.consumer import Consumer


logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


def main():
    rabbitmq_url = os.environ.get("RABBITMQ_URL")
    if not rabbitmq_url:
        raise ValueError("RABBITMQ_URL n'est pas défini dans l'environnement.")

    logging.info("[Main] Démarrage du prix-milvus-processor...")

    # Démarrer le serveur Prometheus pour les métriques
    try:
        start_http_server(8010)
        logging.info("[Main] Serveur Prometheus démarré sur le port 8010.")
    except Exception as e:
        logging.warning(f"[Main] Impossible de démarrer le serveur Prometheus : {e}")

    # Connexion RabbitMQ
    logging.info("[Main] Connexion à RabbitMQ...")
    connection = pika.BlockingConnection(pika.URLParameters(rabbitmq_url))
    logging.info("[Main] ✓ Connecté à RabbitMQ.")

    # Initialiser Publisher et Consumer
    publisher = Publisher(connection)
    consumer = Consumer(connection, publisher)

    # Démarrer la consommation des messages
    logging.info(
        "[Main] 🚀 prix-milvus-processor prêt. Démarrage de la consommation..."
    )
    try:
        consumer.start_consuming()
    except KeyboardInterrupt:
        logging.info("[Main] Arrêt demandé par l'utilisateur.")
    except Exception as e:
        logging.error(f"[Main] Erreur fatale : {e}", exc_info=True)
    finally:
        if connection and not connection.is_closed:
            connection.close()
            logging.info("[Main] Connexion RabbitMQ fermée.")


if __name__ == "__main__":
    main()
