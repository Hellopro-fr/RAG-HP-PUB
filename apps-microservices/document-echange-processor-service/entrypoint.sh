#!/bin/bash
# entrypoint.sh
set -e

# Lancer le serveur docext en arrière-plan
# --max_model_len 15000 \
# --max_gen_tokens 15000 \
VLLM_PORT="8181"
# Le port où docext.app.app lui-même écoute (si c'est un proxy ou une API frontale pour vLLM)
DOCEXT_APP_PORT="8559"

python -m docext.app.app \
  --model_name hosted_vllm/nanonets/Nanonets-OCR-s \
  --gpu_memory_utilization 0.95 \
  --concurrency_limit 2 \
  --max_num_imgs 2 \
  --dtype float16 \
  --server_port "${DOCEXT_APP_PORT}" \
  --vlm_server_port "${VLLM_PORT}"

# Lancer ton application principale
python -u -m document_echange_processor_service.main
