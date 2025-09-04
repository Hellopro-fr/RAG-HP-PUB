import pika
import time
import os

# Importer les modules nécessaires
import torch
from sentence_transformers import SentenceTransformer

# Importer les modules locaux
from embedding_service.messaging.consumer import Consumer
from embedding_service.messaging.publisher import Publisher

from transformers import AutoTokenizer # pour encoder du modèle d'embedding

def main():
    """
    Point d'entrée principal du service.
    Met en place la connexion et lance les composants.
    """
    rabbitmq_url = os.environ.get("RABBITMQ_URL", "amqp://user:password@localhost:5672/")
    connection = None

    # Boucle de connexion robuste
    for i in range(10):
        try:
            connection = pika.BlockingConnection(pika.URLParameters(rabbitmq_url))
            print("✅ Embedding-Product-Processor: Connecté à RabbitMQ.")
            break
        except pika.exceptions.AMQPConnectionError:
            print(f"⏳ Embedding-Product-Processor: En attente de RabbitMQ... {i+1}s")
            time.sleep(1)

    if not connection:
        print("❌ Embedding-Product-Processor: Impossible de se connecter, arrêt du service.")
        exit(1)

    try:
        # 1. Créer une instance du publisher
        publisher = Publisher(connection)

        device = 'cuda' if torch.cuda.is_available() else 'cpu'

        model_name = "dangvantuan/sentence-camembert-large"
        
        tokenizer = AutoTokenizer.from_pretrained(model_name)

        # def hf_length_function(text: str) -> int:
        #     """Compte les tokens avec CamemBERT"""
        #     return len(tokenizer.encode(text, add_special_tokens=False))

        print(f"🔍 Chargement du modèle '{model_name}' sur le device '{device}'...")

        model = SentenceTransformer(model_name, device=device)
        
        
        # 3. Créer une instance du consumer et lui passer le publisher
        consumer = Consumer(connection, publisher, model=model, tokenizer=tokenizer)
        
        # 4. Lancer l'écoute
        consumer.start_consuming()

    except KeyboardInterrupt:
        print("\n🛑 Embedding-Product-Processor: Arrêt demandé.")
    finally:
        if connection and not connection.is_closed:
            connection.close()
            print("✅ Embedding-Product-Processor: Connexion RabbitMQ fermée.")

if __name__ == '__main__':
    main()