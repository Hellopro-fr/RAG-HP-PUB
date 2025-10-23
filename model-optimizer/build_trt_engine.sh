#!/bin/bash
set -e

# Ce script, maintenant exécuté par un service Docker, compile le modèle.

# --- Configuration ---
MODEL_NAME="${MODEL_NAME:-Qwen/Qwen3-14B}"
# Le répertoire de sortie est maintenant /output, monté via docker-compose
OUTPUT_DIR="/output"

# --- Préparation ---
echo "INFO: Démarrage de la compilation du moteur TensorRT-LLM pour le modèle ${MODEL_NAME}"

# Le répertoire de sortie est déjà monté, on s'assure que les sous-dossiers existent.
mkdir -p "${OUTPUT_DIR}/tensorrt_llm/1"
mkdir -p "${OUTPUT_DIR}/tensorrt_llm_bls"

# --- Compilation ---
echo 'INFO: Clonage du modèle depuis le Hub...'
git lfs install
git clone https://huggingface.co/${MODEL_NAME} /tmp/model_hf

echo 'INFO: Démarrage de la compilation du moteur... (cela peut prendre 30-60 minutes)'
trtllm build --model_dir /tmp/model_hf \
             --output_dir ${OUTPUT_DIR}/tensorrt_llm/1 \
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

echo 'INFO: Compilation terminée avec succès.'

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
