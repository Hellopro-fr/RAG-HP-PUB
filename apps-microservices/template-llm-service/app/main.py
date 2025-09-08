import pika
import time
import os
from vllm import LLM

# On utilise des imports absolus basés sur le nom du module qui sera dans le PYTHONPATH
from template_llm_service.messaging.consumer import Consumer
from template_llm_service.messaging.publisher import Publisher

def main():
    """
    Point d'entrée principal du service.
    Charge le modèle LLM et lance les composants RabbitMQ.
    """
    rabbitmq_url = os.environ.get("RABBITMQ_URL")
    if not rabbitmq_url:
        print("❌ ERREUR: La variable d'environnement RABBITMQ_URL n'est pas définie.")
        exit(1)

    print("🚀 template-llm-service: Démarrage...")
    print("🧠 Chargement du modèle LLM (cela peut prendre plusieurs minutes)...")
    llm_config = {
        "model": "Qwen/Qwen3-14B-AWQ",
        "quantization": "awq",
        "gpu_memory_utilization": 0.85,
        "trust_remote_code": True,
        "dtype": "auto",
        "max_model_len": 4096
    }
    try:
        llm = LLM(**llm_config)
        tokenizer = llm.get_tokenizer()
        print("✅ Modèle LLM chargé avec succès.")
    except Exception as e:
        print(f"❌ ERREUR CRITIQUE: Impossible de charger le modèle LLM. Arrêt du service. Erreur: {e}")
        exit(1)

    connection = None
    for i in range(10):
        try:
            connection = pika.BlockingConnection(pika.URLParameters(rabbitmq_url))
            print("✅ template-llm-service: Connecté à RabbitMQ.")
            break
        except pika.exceptions.AMQPConnectionError:
            print(f"⏳ template-llm-service: En attente de RabbitMQ... {i+1}s")
            time.sleep(1)

    if not connection:
        print("❌ template-llm-service: Impossible de se connecter, arrêt du service.")
        exit(1)

    try:
        publisher = Publisher(connection)
        consumer = Consumer(connection, publisher, llm, tokenizer, llm_config)
        consumer.start_consuming()
    except KeyboardInterrupt:
        print("\n🛑 template-llm-service: Arrêt demandé.")
    finally:
        if connection and not connection.is_closed:
            connection.close()
            print("✅ template-llm-service: Connexion RabbitMQ fermée.")

if __name__ == '__main__':
    main()
