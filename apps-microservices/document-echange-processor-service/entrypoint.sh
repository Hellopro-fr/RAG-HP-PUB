#!/bin/bash
# entrypoint.sh
set -e

# Lancer le serveur docext en arrière-plan
python -m docext.app.app \
  --model_name hosted_vllm/nanonets/Nanonets-OCR-s \
  --gpu_memory_utilization 0.95 \
  --max_model_len 10000 \
  --max_gen_tokens 24000 \
  --concurrency_limit 2 \
  --max_num_imgs 2 \
  --dtype float16 \
  --server_port 9998 &

# Lancer ton application principale
python -u -m document_echange_processor_service.main
