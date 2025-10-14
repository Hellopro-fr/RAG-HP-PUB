#!/bin/bash
# entrypoint.sh
set -e

# Lancer le serveur docext en arrière-plan
# --max_model_len 15000 \
# --max_gen_tokens 15000 \
VLLM_HOST="127.0.0.1"
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
  --vlm_server_port "${VLLM_PORT}" &

DOCEXT_APP_PID=$! # Capturer le PID du processus docext.app.app pour le surveiller

# Temps d'attente maximum pour la disponibilité de vLLM
TIMEOUT=300 # Secondes
ELAPSED_TIME=0

echo "Waiting for vLLM server to be ready on ${VLLM_HOST}:${VLLM_PORT}..."
while ! nc -z "${VLLM_HOST}" "${VLLM_PORT}" >/dev/null 2>&1; do
  # Vérifier si le processus docext.app.app est toujours en cours d'exécution
  if ! kill -0 "$DOCEXT_APP_PID" 2>/dev/null; then
    echo "ERROR: docext.app.app process (PID $DOCEXT_APP_PID) has terminated unexpectedly."
    exit 1
  fi

  if [ "${ELAPSED_TIME}" -ge "${TIMEOUT}" ]; then
    echo "ERROR: vLLM server did not become ready within ${TIMEOUT} seconds. Exiting."
    exit 1
  fi
  echo "vLLM not ready yet on ${VLLM_HOST}:${VLLM_PORT}. Retrying in 5 seconds..."
  sleep 5
  ELAPSED_TIME=$((ELAPSED_TIME + 5))
done
echo "vLLM server (via docext.app.app) is ready!"

# Lancer ton application principale
python -u -m document_echange_processor_service.main
