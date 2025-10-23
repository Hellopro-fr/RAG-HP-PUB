import os
import subprocess
import shutil
from huggingface_hub import snapshot_download

# --- Configuration ---
MODEL_NAME = os.getenv("MODEL_NAME", "Qwen/Qwen3-14B")
OUTPUT_DIR = "/output"

def run_command(command: str, error_message: str):
    """Exécute une commande shell et lève une exception en cas d'échec."""
    print(f"INFO: Exécution de la commande -> {command}")
    try:
        subprocess.run(command, shell=True, check=True, text=True)
    except subprocess.CalledProcessError as e:
        print(f"ERREUR: {error_message}")
        print(f"Détails: {e}")
        raise

def build_engine():
    """Orchestre la compilation du modèle en moteur TensorRT-LLM."""
    print(f"--- Début de la compilation du moteur TensorRT-LLM pour le modèle {MODEL_NAME} ---")

    # --- Préparation des répertoires ---
    trt_engine_dir = os.path.join(OUTPUT_DIR, "tensorrt_llm", "1")
    model_repo_dir = os.path.join(OUTPUT_DIR, "tensorrt_llm")
    hf_model_dir = "/tmp/model_hf"

    print(f"INFO: Nettoyage du répertoire de sortie: {OUTPUT_DIR}")
    if os.path.exists(OUTPUT_DIR):
        shutil.rmtree(OUTPUT_DIR)
    
    print("INFO: Création de l'arborescence pour Triton...")
    os.makedirs(trt_engine_dir)

    # --- Étape 1: Télécharger le modèle avec huggingface_hub ---
    print(f"INFO: Téléchargement du modèle {MODEL_NAME} depuis le Hub...")
    try:
        snapshot_download(
            repo_id=MODEL_NAME, 
            local_dir=hf_model_dir, 
            local_dir_use_symlinks=False, # Important pour la compatibilité Docker
            ignore_patterns=["*.safetensors.index.json", "*.onnx", "*.onnx_data"]
        )
    except Exception as e:
        print(f"ERREUR: Le téléchargement du modèle a échoué: {e}")
        raise
    print("INFO: Téléchargement du modèle terminé.")

    # --- Étape 2: Compiler le modèle ---
    print("INFO: Démarrage de la compilation du moteur... (cela peut prendre 30-60 minutes)")
    build_command = f"""
    trtllm build --model_dir {hf_model_dir} \
                 --output_dir {trt_engine_dir} \
                 --dtype bfloat16 \
                 --gpt_attention_plugin bfloat16 \
                 --gemm_plugin bfloat16 \
                 --max_batch_size 32 \
                 --max_input_len 15360 \
                 --max_output_len 1024 \
                 --max_beam_width 1 \
                 --remove_input_padding \
                 --paged_kv_cache \
                 --tp_size 2
    """
    run_command(build_command, "La compilation du moteur TensorRT-LLM a échoué.")

    # --- Étape 3: Créer le config.pbtxt ---
    print("INFO: Création du fichier de configuration config.pbtxt pour Triton...")
    config_pbtxt_content = f"""
name: "tensorrt_llm"
backend: "tensorrtllm"
max_batch_size: 32

parameters: {{
  key: "model_type",
  value: {{ string_value: "inflight_batching_llm" }}
}}

input [ {{
    name: "text_input"
    data_type: TYPE_STRING
    dims: [ -1 ]
  }}, {{
    name: "max_tokens"
    data_type: TYPE_UINT32
    dims: [ 1 ]
    optional: true
  }}, {{
    name: "bad_words"
    data_type: TYPE_STRING
    dims: [ -1 ]
    optional: true
  }}, {{
    name: "stop_words"
    data_type: TYPE_STRING
    dims: [ -1 ]
    optional: true
  }}, {{
    name: "temperature"
    data_type: TYPE_FP32
    dims: [ 1 ]
    optional: true
  }}, {{
    name: "top_k"
    data_type: TYPE_UINT32
    dims: [ 1 ]
    optional: true
  }}, {{
    name: "top_p"
    data_type: TYPE_FP32
    dims: [ 1 ]
    optional: true
  }}, {{
    name: "repetition_penalty"
    data_type: TYPE_FP32
    dims: [ 1 ]
    optional: true
  }}
]

output [ {{
    name: "text_output"
    data_type: TYPE_STRING
    dims: [ -1 ]
  }}
]
"""
    with open(os.path.join(model_repo_dir, "config.pbtxt"), "w") as f:
        f.write(config_pbtxt_content)

    print(f"--- SUCCESS: Le répertoire du modèle Triton '{OUTPUT_DIR}' est prêt. ---")

if __name__ == "__main__":
    build_engine()

