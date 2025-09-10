import pika
import time
import os
from vllm import LLM

# Imports maison
from template_llm_service.messaging.consumer import Consumer
from template_llm_service.messaging.publisher import Publisher

def main():
    """
    Point d'entrée principal du service (mode batch).
    Charge le modèle LLM et lance RabbitMQ.
    """
    rabbitmq_url = os.environ.get("RABBITMQ_URL")
    if not rabbitmq_url:
        print("❌ ERREUR: La variable d'environnement RABBITMQ_URL n'est pas définie.")
        exit(1)

    print("🚀 template-llm-service: Démarrage en mode batch...")
    print("🧠 Chargement du modèle LLM (cela peut prendre plusieurs minutes)...")

    llm_config = {
        "model": "Qwen/Qwen3-14B-AWQ",
        "quantization": "awq",
        "tensor_parallel_size": 2,
        "gpu_memory_utilization": 0.95,
        "trust_remote_code": True,
        "dtype": "auto",
        "max_model_len": 4096,
        "swap_space": 4,
        "max_num_seqs": 64,           # batch max (séquences simultanées)
        "max_num_batched_tokens": 4096,
        "enable_prefix_caching": True,
        "disable_log_stats": True,
    }

    try:
        llm = LLM(**llm_config)
        tokenizer = llm.get_tokenizer()
        print("✅ Modèle LLM chargé avec succès.")

        # Warmup
        from vllm import SamplingParams
        warmup_params = SamplingParams(temperature=0.7, max_tokens=10)
        llm.generate("Hello", warmup_params)
        print("🔥 Modèle préchauffé.")

    except Exception as e:
        print(f"❌ ERREUR CRITIQUE: Impossible de charger le modèle LLM. Erreur: {e}")
        exit(1)

    connection = None
    for i in range(10):
        try:
            connection = pika.BlockingConnection(pika.URLParameters(rabbitmq_url))
            print("✅ Connecté à RabbitMQ.")
            break
        except pika.exceptions.AMQPConnectionError:
            print(f"⏳ Tentative {i+1}: RabbitMQ pas dispo...")
            time.sleep(1)

    if not connection:
        print("❌ Impossible de se connecter à RabbitMQ, arrêt.")
        exit(1)

    try:
        publisher = Publisher(connection)
        consumer = Consumer(connection, publisher, llm, tokenizer, llm_config)
        consumer.start_consuming()
    except KeyboardInterrupt:
        print("\n🛑 Arrêt demandé (CTRL+C).")
    finally:
        if connection and not connection.is_closed:
            connection.close()
            print("✅ Connexion RabbitMQ fermée.")

if __name__ == '__main__':
    import torch
    torch.backends.cuda.matmul.allow_tf32 = True
    torch.backends.cudnn.allow_tf32 = True
    main()
