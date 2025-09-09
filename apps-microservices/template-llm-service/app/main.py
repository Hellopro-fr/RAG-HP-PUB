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
    
    # Configuration optimisée mais compatible avec LLM synchrone
    llm_config = {
        "model": "Qwen/Qwen3-14B-AWQ",
        "quantization": "awq_marlin",
        "tensor_parallel_size": 2,  # Utilise les 2 GPUs
        "gpu_memory_utilization": 0.95,  # Plus agressif avec AWQ
        "trust_remote_code": True,
        "dtype": "auto",
        "max_model_len": 4096,
        "swap_space": 4,  # GB de swap pour gérer les pics
        "max_num_seqs": 64,  # Réduit pour éviter les timeouts
        "max_num_batched_tokens": 4096,  # Plus conservateur
        "enable_prefix_caching": True,  # Cache les préfixes communs
        "disable_log_stats": True,  # Réduit l'overhead
    }
    
    try:
        # Utilise le LLM synchrone standard (plus simple)
        llm = LLM(**llm_config)
        tokenizer = llm.get_tokenizer()  # ✅ Maintenant défini
        print("✅ Modèle LLM chargé avec succès sur 2 GPUs.")
        
        # Warmup simple
        print("🔥 Préchauffage du modèle...")
        from vllm import SamplingParams
        warmup_params = SamplingParams(temperature=0.7, max_tokens=10)
        llm.generate("Hello", warmup_params)
        print("✅ Modèle préchauffé.")
        
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
        publisher = Publisher()
        consumer = Consumer(connection, publisher, llm, tokenizer, llm_config)
        consumer.start_consuming()
    except KeyboardInterrupt:
        print("\n🛑 template-llm-service: Arrêt demandé.")
    finally:
        if connection and not connection.is_closed:
            connection.close()
            print("✅ template-llm-service: Connexion RabbitMQ fermée.")

if __name__ == '__main__':
    # Optimisations PyTorch
    import torch
    torch.backends.cuda.matmul.allow_tf32 = True
    torch.backends.cudnn.allow_tf32 = True
    
    main()