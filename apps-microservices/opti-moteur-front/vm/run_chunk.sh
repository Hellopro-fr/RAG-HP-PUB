#!/bin/bash
# run_chunk.sh
# =============
# Lance l'ingestion d'UN chunk de categories avec :
#   - Garde-fou disque (DISK_THRESHOLD_GB)
#   - Logs daté dans /tmp/
#   - Trap Ctrl+C pour arret propre
#   - Affichage clair de la progression
#
# Usage :
#   ./run_chunk.sh categories_missing_chunk_001_of_023.txt
#   ./run_chunk.sh categories_missing_chunk_001_of_023.txt produits_prod
#
# Pour arreter pendant l'execution :
#   Ctrl+C OU kill -SIGTERM <PID>

set -e

# === ARGS ===
CHUNK_FILE="${1:-}"
TS_COLLECTION="${2:-produits_prod}"

if [ -z "$CHUNK_FILE" ]; then
    echo "[ERREUR] Usage: $0 <chunk_file.txt> [ts_collection]"
    echo ""
    echo "Exemples :"
    echo "  $0 ../../../rubriques/categories_missing_chunk_001_of_023.txt"
    echo "  $0 ../../../rubriques/categories_missing_chunk_001_of_023.txt produits_prod"
    exit 1
fi

if [ ! -f "$CHUNK_FILE" ]; then
    echo "[ERREUR] Fichier $CHUNK_FILE introuvable"
    exit 1
fi

# === CONFIG ===
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DISK_THRESHOLD_GB="${DISK_THRESHOLD_GB:-3.0}"
CHUNK_NAME="$(basename "$CHUNK_FILE" .txt)"
LOG_FILE="/tmp/ingest_${CHUNK_NAME}_$(date +%Y%m%d_%H%M%S).log"
PIDFILE="/tmp/ingest_${CHUNK_NAME}.pid"

# === HEALTH CHECKS ===
echo "=========================================="
echo "Run chunk : $CHUNK_FILE"
echo "Collection: $TS_COLLECTION"
echo "Log file  : $LOG_FILE"
echo "Disk min  : $DISK_THRESHOLD_GB GB"
echo "=========================================="

# Verifier l'espace disque AVANT
disk_now=$(df -BG --output=avail / | tail -1 | tr -dc '0-9')
echo "[INFO] Espace disque actuel : ${disk_now} GB"
if [ "$disk_now" -lt "$(echo "$DISK_THRESHOLD_GB" | cut -d. -f1)" ]; then
    echo "[ERREUR] Espace disque (${disk_now} GB) < seuil ($DISK_THRESHOLD_GB GB). ABORT."
    exit 2
fi

# Verifier env vars Milvus + Typesense
for var in MILVUS_HOST MILVUS_PORT TS_HOST TS_PORT TS_API_KEY; do
    if [ -z "${!var}" ]; then
        echo "[ERREUR] Variable $var manquante. Source .env d'abord :"
        echo "  cd /home/devhp/RAG-HP-PUB/apps-microservices/opti-moteur-front"
        echo "  export \$(grep -E '^(ZILLIZ_|MILVUS_|TS_)' .env | xargs)"
        echo "  export MILVUS_HOST=\$ZILLIZ_URI MILVUS_PORT=\$ZILLIZ_PORT"
        echo "  export MILVUS_USER=\$ZILLIZ_USER MILVUS_PASSWORD=\$ZILLIZ_PASSWORD"
        exit 3
    fi
done

# === LANCEMENT ===
nb_cats=$(grep -cv "^#" "$CHUNK_FILE" | grep -v "^$" | wc -l)
echo "[INFO] $nb_cats categories dans ce chunk"
echo ""

# Trap Ctrl+C : kill le PID enfant proprement
cleanup() {
    if [ -f "$PIDFILE" ]; then
        local pid=$(cat "$PIDFILE")
        echo ""
        echo "[CLEANUP] Stopping PID $pid..."
        kill -SIGTERM "$pid" 2>/dev/null || true
        sleep 2
        kill -SIGKILL "$pid" 2>/dev/null || true
        rm -f "$PIDFILE"
    fi
    echo "[CLEANUP] Done. Log : $LOG_FILE"
}
trap cleanup EXIT INT TERM

# Lancer en background mais wait sur lui
export CATEGORIES_FILE="$CHUNK_FILE"
export TS_COLLECTION="$TS_COLLECTION"
export DISK_THRESHOLD_GB="$DISK_THRESHOLD_GB"

python3 -u "$SCRIPT_DIR/ingest_by_categories.py" > "$LOG_FILE" 2>&1 &
PID=$!
echo $PID > "$PIDFILE"
echo "[INFO] PID enfant : $PID"
echo "[INFO] Pour suivre en direct : tail -f $LOG_FILE"
echo "[INFO] Pour arreter : Ctrl+C OU kill $PID"
echo ""

# Suivi en tail -f tant que le process tourne
tail -f "$LOG_FILE" &
TAIL_PID=$!

wait $PID 2>/dev/null
EXIT_CODE=$?

kill $TAIL_PID 2>/dev/null || true
rm -f "$PIDFILE"

echo ""
echo "=========================================="
if [ $EXIT_CODE -eq 0 ]; then
    echo "[DONE] Chunk termine avec succes"
else
    echo "[ERREUR] Chunk termine avec code $EXIT_CODE"
fi

# Stats finales
disk_after=$(df -BG --output=avail / | tail -1 | tr -dc '0-9')
echo "[INFO] Disque libre : ${disk_now} GB -> ${disk_after} GB (-$((disk_now - disk_after)) GB)"
echo "[INFO] Log complet  : $LOG_FILE"
echo "=========================================="

exit $EXIT_CODE
