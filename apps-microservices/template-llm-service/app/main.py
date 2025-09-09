import pika
import time
import os
import torch
import subprocess
from vllm import LLM

# On utilise des imports absolus basés sur le nom du module qui sera dans le PYTHONPATH
from template_llm_service.messaging.consumer import Consumer
from template_llm_service.messaging.publisher import Publisher

def check_gpu_availability():
    """
    Détecte combien de GPUs sont réellement disponibles et utilisables
    """
    print("🔍 Vérification de la disponibilité des GPUs...")
    
    if not torch.cuda.is_available():
        print("❌ CUDA non disponible")
        return 0, []
    
    total_gpus = torch.cuda.device_count()
    print(f"📊 {total_gpus} GPU(s) détecté(s) par CUDA")
    
    available_gpus = []
    
    for i in range(total_gpus):
        try:
            # Test d'allocation mémoire sur chaque GPU
            device = torch.device(f'cuda:{i}')
            
            # Vérifie la mémoire libre
            torch.cuda.set_device(i)
            memory_free = torch.cuda.get_device_properties(i).total_memory
            memory_allocated = torch.cuda.memory_allocated(i)
            memory_cached = torch.cuda.memory_reserved(i)
            memory_available = memory_free - memory_allocated - memory_cached
            
            # Seuil minimum : 6GB libre pour un modèle 14B
            min_memory_gb = 6 * 1024**3  # 6GB en bytes
            
            if memory_available > min_memory_gb:
                # Test d'allocation simple
                test_tensor = torch.randn(1000, 1000, device=device)
                del test_tensor
                torch.cuda.empty_cache()
                
                available_gpus.append(i)
                print(f"✅ GPU {i}: Disponible ({memory_available/1024**3:.1f}GB libres)")
            else:
                print(f"⚠️  GPU {i}: Mémoire insuffisante ({memory_available/1024**3:.1f}GB libres)")
                
        except Exception as e:
            print(f"❌ GPU {i}: Non disponible - {e}")
    
    print(f"🎯 GPUs utilisables : {available_gpus}")
    return len(available_gpus), available_gpus

def get_optimal_llm_config(available_gpu_count, available_gpu_ids):
    """
    Génère la configuration optimale selon le nombre de GPUs disponibles
    Compatible avec Docker compose flexible
    """
    base_config = {
        "model": "Qwen/Qwen3-14B-AWQ",
        "quantization": "awq",
        "trust_remote_code": True,
        "dtype": "auto",
        "max_model_len": 4096,
        "disable_log_stats": True,
    }
    
    # Vérifie si CUDA_VISIBLE_DEVICES est déjà défini par Docker
    cuda_visible = os.environ.get('CUDA_VISIBLE_DEVICES')
    preferred_gpu_count = int(os.environ.get('PREFERRED_GPU_COUNT', 2))
    
    if cuda_visible:
        print(f"🔍 CUDA_VISIBLE_DEVICES défini par Docker: {cuda_visible}")
        # Docker a déjà limité les GPUs, utilise ce qui est disponible
        effective_gpu_count = min(available_gpu_count, preferred_gpu_count)
    else:
        # Python contrôle complètement les GPUs
        effective_gpu_count = min(available_gpu_count, preferred_gpu_count)
        if effective_gpu_count >= 2:
            os.environ['CUDA_VISIBLE_DEVICES'] = ','.join(map(str, available_gpu_ids[:2]))
        elif effective_gpu_count == 1:
            os.environ['CUDA_VISIBLE_DEVICES'] = str(available_gpu_ids[0])
    
    if effective_gpu_count >= 2:
        print(f"🚀 Configuration Multi-GPU ({effective_gpu_count} GPUs)")
        config = {
            **base_config,
            "tensor_parallel_size": 2,
            "gpu_memory_utilization": 0.95,
            "max_num_seqs": 32,  # Optimisé pour classification rapide
            "max_num_batched_tokens": 2048,
            "enable_prefix_caching": True,
            "enforce_eager": True,  # Plus rapide pour petites requêtes
        }
        
    elif effective_gpu_count == 1:
        print("⚡ Configuration Single-GPU")
        config = {
            **base_config,
            "tensor_parallel_size": 1,
            "gpu_memory_utilization": 0.90,
            "max_num_seqs": 16,  # Plus conservateur
            "max_num_batched_tokens": 1024,
            "enable_prefix_caching": True,
            "swap_space": 4,
            "enforce_eager": True,
        }
        
    else:
        print("❌ Aucun GPU utilisable détecté")
        raise RuntimeError("Aucun GPU disponible avec suffisamment de mémoire")
    
    return config

def monitor_gpu_usage():
    """
    Monitore l'utilisation GPU pendant l'exécution (optionnel)
    """
    try:
        result = subprocess.run(['nvidia-smi', '--query-gpu=utilization.gpu,memory.used,memory.total', 
                               '--format=csv,noheader,nounits'], 
                              capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            for i, line in enumerate(lines):
                gpu_util, mem_used, mem_total = line.split(', ')
                print(f"📊 GPU {i}: {gpu_util}% utilisation, {mem_used}/{mem_total}MB mémoire")
    except:
        pass  # Ignore les erreurs de monitoring

def main():
    """
    Point d'entrée principal du service avec adaptation GPU automatique.
    """
    rabbitmq_url = os.environ.get("RABBITMQ_URL")
    if not rabbitmq_url:
        print("❌ ERREUR: La variable d'environnement RABBITMQ_URL n'est pas définie.")
        exit(1)

    print("🚀 template-llm-service: Démarrage adaptatif...")
    
    # 🎯 DÉTECTION AUTOMATIQUE DES GPUs
    available_gpu_count, available_gpu_ids = check_gpu_availability()
    
    if available_gpu_count == 0:
        print("❌ Aucun GPU disponible, arrêt du service.")
        exit(1)
    
    # 🔧 CONFIGURATION ADAPTATIVE
    llm_config = get_optimal_llm_config(available_gpu_count, available_gpu_ids)
    
    print("🧠 Chargement du modèle LLM adaptatif...")
    print(f"   📋 Configuration: tensor_parallel_size={llm_config['tensor_parallel_size']}")
    
    try:
        # Optimisations PyTorch
        torch.backends.cuda.matmul.allow_tf32 = True
        torch.backends.cudnn.allow_tf32 = True
        
        llm = LLM(**llm_config)
        tokenizer = llm.get_tokenizer()
        
        print(f"✅ Modèle LLM chargé avec succès sur {available_gpu_count} GPU(s).")
        
        # Monitoring initial
        monitor_gpu_usage()
        
        # Warmup simple adaptatif
        print("🔥 Préchauffage du modèle...")
        from vllm import SamplingParams
        warmup_params = SamplingParams(temperature=0.7, max_tokens=10)
        llm.generate("Test", warmup_params)
        print("✅ Modèle préchauffé.")
        
    except Exception as e:
        print(f"❌ ERREUR CRITIQUE: Impossible de charger le modèle LLM. Erreur: {e}")
        print("💡 Tentative de fallback en single-GPU...")
        
        if available_gpu_count > 1:
            # Retry en single GPU
            llm_config = get_optimal_llm_config(1, available_gpu_ids[:1])
            try:
                llm = LLM(**llm_config)
                tokenizer = llm.get_tokenizer()
                print("✅ Fallback réussi : modèle chargé en single-GPU")
            except Exception as e2:
                print(f"❌ Fallback échoué : {e2}")
                exit(1)
        else:
            exit(1)

    # Connexion RabbitMQ (code existant)
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
        
        print(f"🎯 Service démarré avec {available_gpu_count} GPU(s)")
        monitor_gpu_usage()
        
        consumer.start_consuming()
        
    except KeyboardInterrupt:
        print("\n🛑 template-llm-service: Arrêt demandé.")
    finally:
        if connection and not connection.is_closed:
            connection.close()
            print("✅ template-llm-service: Connexion RabbitMQ fermée.")

if __name__ == '__main__':
    main()