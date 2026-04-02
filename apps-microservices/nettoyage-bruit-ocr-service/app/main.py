import os
import asyncio
import aio_pika
import aiormq
from nettoyage_bruit_ocr_service.messaging.publisher import Publisher
from nettoyage_bruit_ocr_service.messaging.consumer import Consumer

async def main():
    """
    Point d'entree principal asynchrone du service.
    Met en place la connexion et lance les composants.
    """
    rabbitmq_url = os.environ.get("RABBITMQ_URL")
    if not rabbitmq_url:
        print("ERREUR: La variable d'environnement RABBITMQ_URL n'est pas definie.")
        exit(1)

    print("Nettoyage-bruit-ocr-service: Demarrage...")

    while True:
        try:
            connection = await aio_pika.connect_robust(
                rabbitmq_url,
                heartbeat=3600,
                connection_timeout=7200
            )
            print("Nettoyage-bruit-ocr-service: Connecte a RabbitMQ.")

            async with connection:
                publisher = Publisher(connection)
                consumer = Consumer(connection, publisher)

                await consumer.start_consuming()

                # Keep the service alive
                await asyncio.Future()

        except (aiormq.exceptions.AMQPConnectionError, aiormq.exceptions.ChannelInvalidStateError) as e:
            print(f"Erreur de connexion RabbitMQ: {e}. Tentative de reconnexion dans 10 secondes...")
            await asyncio.sleep(10)
        except KeyboardInterrupt:
            print("Nettoyage-bruit-ocr-service: Arret demande.")
            break
        except Exception as e:
            print(f"Erreur inattendue dans main: {e}. Redemarrage dans 10 secondes...")
            await asyncio.sleep(10)

    print("Nettoyage-bruit-ocr-service: Service arrete.")


if __name__ == '__main__':
    asyncio.run(main())
