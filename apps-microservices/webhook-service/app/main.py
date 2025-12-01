import pika
import time
import os
import sys
import logging
from webhook_service.messaging.consumer import Consumer

# Configuration du logging structuré
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def validate_environment():
    """
    Valide que toutes les variables d'environnement requises sont définies.

    Returns:
        bool: True si toutes les variables sont présentes, False sinon
    """
    required_vars = {
        "RABBITMQ_URL": "URL de connexion RabbitMQ",
        "KEY_WEBHOOK": "Clé secrète pour signer les webhooks"
    }

    missing_vars = []
    for var, description in required_vars.items():
        if not os.environ.get(var):
            missing_vars.append(f"  - {var}: {description}")

    if missing_vars:
        logger.critical("❌ Variables d'environnement manquantes:")
        for var in missing_vars:
            logger.critical(var)
        logger.critical(
            "\n💡 Veuillez définir ces variables dans votre fichier .env ou variables d'environnement.\n"
            "   Exemple .env:\n"
            "   RABBITMQ_URL=amqp://user:password@localhost:5672/\n"
            "   KEY_WEBHOOK=your_secret_webhook_key_here\n"
        )
        return False

    return True


def connect_to_rabbitmq(rabbitmq_url: str, max_retries: int = 10, retry_delay: int = 1):
    """
    Établit une connexion à RabbitMQ avec retry logic.

    Args:
        rabbitmq_url: URL de connexion RabbitMQ
        max_retries: Nombre maximum de tentatives
        retry_delay: Délai en secondes entre chaque tentative

    Returns:
        pika.BlockingConnection: Connexion établie
        None: Si la connexion a échoué après toutes les tentatives

    Raises:
        SystemExit: Si impossible de se connecter après max_retries
    """
    connection = None

    logger.info(f"🔌 Tentative de connexion à RabbitMQ...")

    for attempt in range(1, max_retries + 1):
        try:
            connection = pika.BlockingConnection(pika.URLParameters(rabbitmq_url))
            logger.info("✅ webhook-service: Connexion à RabbitMQ établie avec succès")
            return connection

        except pika.exceptions.AMQPConnectionError as e:
            if attempt < max_retries:
                logger.warning(
                    f"⏳ webhook-service: En attente de RabbitMQ "
                    f"(tentative {attempt}/{max_retries})... Retry dans {retry_delay}s"
                )
                time.sleep(retry_delay)
            else:
                logger.critical(
                    f"❌ webhook-service: Impossible de se connecter à RabbitMQ "
                    f"après {max_retries} tentatives."
                )
                logger.critical(f"   Erreur: {e}")
                logger.critical(f"   URL: {rabbitmq_url}")
                raise SystemExit(1)

    return None


def main():
    """
    Point d'entrée principal du webhook-service.

    1. Valide les variables d'environnement
    2. Établit la connexion RabbitMQ
    3. Initialise le consumer
    4. Lance la consommation des messages
    """
    logger.info("🚀 Démarrage du webhook-service...")

    # 1. Validation des variables d'environnement
    if not validate_environment():
        logger.critical("❌ Arrêt du service: configuration invalide")
        sys.exit(1)

    # 2. Récupération de l'URL RabbitMQ
    rabbitmq_url = os.environ.get("RABBITMQ_URL")
    logger.info(f"Configuration RabbitMQ: {rabbitmq_url.split('@')[1] if '@' in rabbitmq_url else 'localhost'}")

    # 3. Connexion à RabbitMQ
    connection = connect_to_rabbitmq(rabbitmq_url)

    if not connection:
        logger.critical("❌ webhook-service: Échec de connexion RabbitMQ, arrêt du service")
        sys.exit(1)

    try:
        # 4. Créer une instance du consumer
        consumer = Consumer(connection)

        # 5. Lancer l'écoute des messages
        logger.info("🎧 webhook-service: Prêt à traiter les webhooks")
        consumer.start_consuming()

    except KeyboardInterrupt:
        logger.info("\n🛑 webhook-service: Arrêt demandé par l'utilisateur (Ctrl+C)")

    except Exception as e:
        logger.exception(f"❌ webhook-service: Erreur critique: {e}")
        sys.exit(1)

    finally:
        # Fermeture propre de la connexion
        if connection and not connection.is_closed:
            try:
                connection.close()
                logger.info("✅ webhook-service: Connexion RabbitMQ fermée proprement")
            except Exception as e:
                logger.error(f"⚠️ Erreur lors de la fermeture de la connexion: {e}")


if __name__ == '__main__':
    main()
