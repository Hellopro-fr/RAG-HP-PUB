#!/bin/bash
set -e

# Ce script compile un modèle Hugging Face en un moteur TensorRT-LLM optimisé.
# Il doit être exécuté une seule fois par modèle.

# --- Configuration ---
# Le nom du modèle sur le Hub Hugging Face.
MODEL_NAME="${MODEL_NAME:-Qwen/Qwen3-14B}"
# Le répertoire de sortie pour le moteur compilé et le repository Triton.
OUTPUT_DIR="./triton_model_repo"
# Le chemin vers votre cache Hugging Face local pour éviter les re-téléchargements.
HUGGINGFACE_CACHE_DIR="/mnt/data/docker/images/huggingface_cache"

# --- Vérifications Préliminaires ---
echo "INFO: Démarrage de la compilation du moteur TensorRT-LLM pour le modèle ${MODEL_NAME}"

if [ ! -d "${HUGGINGFACE_CACHE_DIR}" ]; then
    echo "AVERTISSEMENT: Le répertoire du cache Hugging Face (${HUGGINGFACE_CACHE_DIR}) n'a pas été trouvé. Le modèle de base sera téléchargé."
    # Créer un dossier temporaire pour le cache si celui spécifié n'existe pas
    HUGGINGFACE_CACHE_DIR="./hf_cache_temp"
    mkdir -p "${HUGGINGFACE_CACHE_DIR}"
fi

# Création du répertoire de sortie pour le modèle Triton
rm -rf "${OUTPUT_DIR}" # Nettoyer les anciennes versions
mkdir -p "${OUTPUT_DIR}/tensorrt_llm/1"
mkdir -p "${OUTPUT_DIR}/tensorrt_llm_bls"


echo "INFO: Lancement du conteneur de compilation TensorRT-LLM..."

# --- Exécution de la Compilation ---
# Nous utilisons `docker run` pour lancer un conteneur de compilation éphémère.
# --gpus all : Donne accès à tous les GPUs
# --rm : Supprime le conteneur après exécution
# -v : Monte les volumes nécessaires (cache, sortie)

docker run --gpus all --rm -it \
  -v "${HUGGINGFACE_CACHE_DIR}:/root/.cache/huggingface" \
  -v "$(pwd)/${OUTPUT_DIR}:/output" \
  nvcr.io/nvidia/tensorrtllm-python:latest-builder \
  bash -c "\
    echo 'INFO: Clonage du modèle depuis le Hub...' && \
    git lfs install && \
    git clone https://huggingface.co/${MODEL_NAME} /tmp/model_hf && \
    
    echo 'INFO: Démarrage de la compilation du moteur... (cela peut prendre 30-60 minutes)' && \
    trtllm build --model_dir /tmp/model_hf \
                 --output_dir /output/tensorrt_llm/1 \
                 --dtype bfloat16 \
                 --gpt_attention_plugin bfloat16 \
                 --gemm_plugin bfloat16 \
                 --max_batch_size 32 \
                 --max_input_len 15360 \
                 --max_output_len 1024 \
                 --max_beam_width 1 \
                 --remove_input_padding \
                 --paged_kv_cache \
                 --tp_size 2 && \
    
    echo 'INFO: Compilation terminée avec succès.' \
  "

# --- Création du config.pbtxt pour Triton ---
echo "INFO: Création du fichier de configuration config.pbtxt pour Triton..."

cat > "${OUTPUT_DIR}/tensorrt_llm/config.pbtxt" <<- EOL
name: "tensorrt_llm"
backend: "tensorrtllm"
max_batch_size: 32

parameters: {
  key: "model_type",
  value: { string_value: "inflight_batching_llm" }
}

input [ { 
    name: "text_input"
    data_type: TYPE_STRING
    dims: [ -1 ]
  }, { 
    name: "max_tokens"
    data_type: TYPE_UINT32
    dims: [ 1 ]
    optional: true
  }, { 
    name: "bad_words"
    data_type: TYPE_STRING
    dims: [ -1 ]
    optional: true
  }, { 
    name: "stop_words"
    data_type: TYPE_STRING
    dims: [ -1 ]
    optional: true
  }, { 
    name: "temperature"
    data_type: TYPE_FP32
    dims: [ 1 ]
    optional: true
  }, { 
    name: "top_k"
    data_type: TYPE_UINT32
    dims: [ 1 ]
    optional: true
  }, { 
    name: "top_p"
    data_type: TYPE_FP32
    dims: [ 1 ]
    optional: true
  }, { 
    name: "repetition_penalty"
    data_type: TYPE_FP32
    dims: [ 1 ]
    optional: true
  }
]

output [ { 
    name: "text_output"
    data_type: TYPE_STRING
    dims: [ -1 ]
  }
]
EOL

echo "SUCCESS: Le répertoire du modèle Triton '${OUTPUT_DIR}' est prêt."
