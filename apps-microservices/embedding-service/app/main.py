import pika, os, time, json

RABBITMQ_URL = os.environ.get("RABBITMQ_URL", "amqp://user:password@localhost:5672/")
EXCHANGE_NAME = 'processed_data_exchange' # Il écoute l'exchange du service précédent
ROUTING_KEY = 'processed_data.product'
QUEUE_NAME = 'embedding_queue'

def on_message_callback(ch, method, properties, body):
    data = json.loads(body)

    # Todo: à modifier selon le flow de l'application
    product_id = data.get("metadata", {}).get('id_produit', 'ID inconnu')
    print(f"\n🤖 Embedding-Service: Message reçu pour '{product_id}'.")

    # Étape 1: Récupérer le texte à "embedder"
    text_to_embed = data.get('embedding', '')
    print(f"   - Texte à embedder: \"{text_to_embed[:50]}...\"")

    # Pour ce test, on s'arrête ici. L'étape suivante serait de publier
    # vers le milvus-loader.

    # Étape 3: Acquitter le message
    ch.basic_ack(delivery_tag=method.delivery_tag)
    print(f"   -> Message pour '{product_id}' acquitté.")

def main():
    connection = pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))
    channel = connection.channel()

    channel.exchange_declare(exchange=EXCHANGE_NAME, exchange_type='topic', durable=True)
    channel.queue_declare(queue=QUEUE_NAME, durable=True)
    channel.queue_bind(exchange=EXCHANGE_NAME, queue=QUEUE_NAME, routing_key=ROUTING_KEY)
    channel.basic_consume(queue=QUEUE_NAME, on_message_callback=on_message_callback)

    print("👂 Embedding-Service: En attente de messages...")
    channel.start_consuming()

if __name__ == '__main__':
    main()
