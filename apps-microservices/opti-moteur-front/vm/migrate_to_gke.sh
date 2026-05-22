#!/usr/bin/env bash
#
# migrate_to_gke.sh
# =================
# Orchestre l'ingestion Milvus -> Typesense GKE en une commande,
# avec checkpoints et logs separes par etape.
#
# Pre-requis :
#   - Tourner sur la VM GCP (acces Milvus + reseau prive GCP)
#   - .env contient ZILLIZ_* + TYPESENSE_* + EMBEDDING_API_*
#   - Connectivite VM -> 10.0.1.240:8570 (Typesense GKE) validee
#
# Usage :
#   cd ~/RAG-HP-PUB/apps-microservices/opti-moteur-front/vm
#   bash migrate_to_gke.sh
#
# Etapes interactives (Y/N a chaque palier). Pour run non-interactif :
#   AUTO=1 bash migrate_to_gke.sh
#
# Reprise :
#   Si une etape echoue, relancer le script : il detectera les fichiers
#   de checkpoint dans /tmp/migrate_gke_checkpoints/ et proposera de
#   reprendre.

set -eu
set -o pipefail

# ========== CONFIG ==========
REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
VM_DIR="$(cd "$(dirname "$0")" && pwd)"
OPTI_FRONT_DIR="$(cd "$VM_DIR/.." && pwd)"

CHECKPOINT_DIR="${CHECKPOINT_DIR:-/tmp/migrate_gke_checkpoints}"
LOG_DIR="${LOG_DIR:-/tmp/migrate_gke_logs}"
mkdir -p "$CHECKPOINT_DIR" "$LOG_DIR"

AUTO="${AUTO:-0}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"

# Cible Typesense GKE (peut etre override par .env / env vars)
TS_HOST="${TS_HOST:-10.0.1.240}"
TS_PORT="${TS_PORT:-8570}"
TS_API_KEY="${TS_API_KEY:-${TYPESENSE_API_KEY:-}}"
TS_COLLECTION="${TS_COLLECTION:-${TYPESENSE_COLLECTION:-produits_prod}}"

# Source Milvus (depuis .env de opti-moteur-front)
if [ -f "$OPTI_FRONT_DIR/.env" ]; then
    set -o allexport
    # shellcheck disable=SC1091
    source "$OPTI_FRONT_DIR/.env"
    set +o allexport
fi
export MILVUS_HOST="${ZILLIZ_URI:-${MILVUS_HOST:-}}"
export MILVUS_PORT="${ZILLIZ_PORT:-${MILVUS_PORT:-19530}}"
export MILVUS_USER="${ZILLIZ_USER:-${MILVUS_USER:-}}"
export MILVUS_PASSWORD="${ZILLIZ_PASSWORD:-${MILVUS_PASSWORD:-}}"
export MILVUS_COLLECTION="${MILVUS_COLLECTION:-produits_3}"

# ========== HELPERS ==========
log() { echo "[$(date +%H:%M:%S)] $*"; }
err() { echo "[$(date +%H:%M:%S)] ERROR: $*" >&2; }

confirm() {
    if [ "$AUTO" = "1" ]; then return 0; fi
    local msg="$1"
    read -r -p "$msg [y/N] " ans
    case "$ans" in [yY]*) return 0 ;; *) return 1 ;; esac
}

step_done() {
    touch "$CHECKPOINT_DIR/$1.done"
}

step_pending() {
    [ ! -f "$CHECKPOINT_DIR/$1.done" ]
}

# ========== ETAPES ==========
preflight() {
    log "=== Preflight ==="
    [ -n "$TS_API_KEY" ] || { err "TS_API_KEY (ou TYPESENSE_API_KEY) manquant"; exit 1; }
    [ -n "$MILVUS_HOST" ] || { err "MILVUS_HOST (ou ZILLIZ_URI) manquant dans .env"; exit 1; }

    log "TS target  : http://$TS_HOST:$TS_PORT/$TS_COLLECTION"
    log "Milvus src : $MILVUS_HOST:$MILVUS_PORT/$MILVUS_COLLECTION"

    if ! curl -sf "http://$TS_HOST:$TS_PORT/health" \
              -H "X-TYPESENSE-API-KEY: $TS_API_KEY" >/dev/null 2>&1; then
        err "Typesense GKE injoignable : http://$TS_HOST:$TS_PORT/health"
        err "Verifier le firewall GCP / VPC privee avec Tafita."
        exit 1
    fi
    log "Typesense GKE OK"

    # Inventaire actuel
    local cur_docs
    cur_docs=$(curl -s "http://$TS_HOST:$TS_PORT/collections/$TS_COLLECTION" \
                    -H "X-TYPESENSE-API-KEY: $TS_API_KEY" 2>/dev/null \
               | jq -r '.num_documents // 0')
    log "Typesense GKE actuellement : $cur_docs docs"
    echo "$cur_docs" > "$CHECKPOINT_DIR/docs_before.txt"
}

step_1_diff_categories() {
    if ! step_pending "step1"; then log "step1 deja fait, skip"; return; fi
    log "=== Etape 1 : diff catégories Milvus vs Typesense GKE ==="
    confirm "Lancer list_missing_categories.py ?" || return

    cd "$VM_DIR"
    python3 list_missing_categories.py 2>&1 | tee "$LOG_DIR/step1_${TIMESTAMP}.log"

    local missing_file="$REPO_ROOT/rubriques/categories_missing.txt"
    if [ ! -f "$missing_file" ]; then
        err "categories_missing.txt non genere"
        return 1
    fi
    local n_missing
    n_missing=$(wc -l < "$missing_file")
    log "Catégories manquantes : $n_missing"
    step_done "step1"
}

step_2_ingest() {
    if ! step_pending "step2"; then log "step2 deja fait, skip"; return; fi
    log "=== Etape 2 : ingestion delta ==="
    local missing_file="$REPO_ROOT/rubriques/categories_missing.txt"
    [ -f "$missing_file" ] || { err "$missing_file absent, refaire step 1"; return 1; }

    local n_missing
    n_missing=$(wc -l < "$missing_file")
    confirm "Ingerer $n_missing catégories ? (~5-8h)" || return

    cd "$VM_DIR"
    export TS_HOST TS_PORT TS_API_KEY TS_COLLECTION
    export EXTRA_FILTER="${EXTRA_FILTER:-etat in [\"Client\",\"Pause\",\"Prospect\"]}"

    local logfile="$LOG_DIR/step2_ingest_${TIMESTAMP}.log"
    log "Lancement en nohup : $logfile"
    nohup python3 ingest_by_categories.py \
        CATEGORIES_FILE="$missing_file" \
        > "$logfile" 2>&1 &
    local pid=$!
    echo "$pid" > "$CHECKPOINT_DIR/step2.pid"
    log "PID : $pid"
    log "Suivre : tail -f $logfile"
    log "Quand termine, relance ce script pour passer a l'etape 3."

    # On ne marque PAS step2 done ici (asynchrone). On verifie a la
    # prochaine invocation.
}

step_2_check() {
    if [ ! -f "$CHECKPOINT_DIR/step2.pid" ]; then return; fi
    if step_pending "step2"; then
        local pid
        pid=$(cat "$CHECKPOINT_DIR/step2.pid")
        if kill -0 "$pid" 2>/dev/null; then
            log "Ingestion encore en cours (PID $pid). Patientez puis relancez."
            exit 0
        else
            log "Ingestion terminee (PID $pid). Verification logs..."
            local logfile
            logfile=$(ls -1t "$LOG_DIR"/step2_ingest_*.log 2>/dev/null | head -1)
            tail -20 "$logfile"
            confirm "Marquer l'etape 2 comme done ?" && step_done "step2"
        fi
    fi
}

step_3_orphans() {
    if ! step_pending "step3"; then log "step3 deja fait, skip"; return; fi
    log "=== Etape 3 : cleanup orphelins ==="
    confirm "Lancer delete_orphans.py en DRY-RUN ?" || return

    cd "$VM_DIR"
    export TS_HOST TS_PORT TS_API_KEY TS_COLLECTION

    DRY_RUN=1 python3 delete_orphans.py 2>&1 | tee "$LOG_DIR/step3_dryrun_${TIMESTAMP}.log"

    confirm "Lancer la suppression reelle des orphelins ?" || return
    python3 delete_orphans.py 2>&1 | tee "$LOG_DIR/step3_real_${TIMESTAMP}.log"
    step_done "step3"
}

step_4_idf() {
    if ! step_pending "step4"; then log "step4 deja fait, skip"; return; fi
    log "=== Etape 4 : regenerer IDF ==="
    confirm "Generer idf_nom_produit.json sur Typesense GKE ?" || return

    cd "$OPTI_FRONT_DIR"
    docker compose exec -e TYPESENSE_HOST="$TS_HOST" \
                        -e TYPESENSE_PORT="$TS_PORT" \
                        -e TYPESENSE_API_KEY="$TS_API_KEY" \
                        opti-moteur-front \
                        python scripts/compute_idf.py \
        2>&1 | tee "$LOG_DIR/step4_idf_${TIMESTAMP}.log"

    if [ -f "$OPTI_FRONT_DIR/app/data/idf_nom_produit.json" ]; then
        local size
        size=$(du -h "$OPTI_FRONT_DIR/app/data/idf_nom_produit.json" | cut -f1)
        log "IDF cree : $size"
        docker compose restart opti-moteur-front
        sleep 5
        docker compose logs --tail 30 opti-moteur-front | grep -i "IDF" || true
        step_done "step4"
    else
        err "idf_nom_produit.json non genere, voir log"
        return 1
    fi
}

step_5_synonyms() {
    if ! step_pending "step5"; then log "step5 deja fait, skip"; return; fi
    log "=== Etape 5 : verif synonymes ==="
    local n_syn
    n_syn=$(curl -s "http://$TS_HOST:$TS_PORT/collections/$TS_COLLECTION/synonyms" \
                 -H "X-TYPESENSE-API-KEY: $TS_API_KEY" \
            | jq -r '.synonyms | length // 0')
    log "Synonymes Typesense GKE : $n_syn clusters"
    if [ "$n_syn" -lt 100 ]; then
        err "Synonymes anormalement bas. Lancer cote PHP :"
        err "  php site/script/typesense/sync_synonyms_daily.php"
    else
        log "Synonymes OK"
        step_done "step5"
    fi
}

summary() {
    log "=== Resume ==="
    local docs_before docs_after
    docs_before=$(cat "$CHECKPOINT_DIR/docs_before.txt" 2>/dev/null || echo "?")
    docs_after=$(curl -s "http://$TS_HOST:$TS_PORT/collections/$TS_COLLECTION" \
                      -H "X-TYPESENSE-API-KEY: $TS_API_KEY" \
                 | jq -r '.num_documents // "?"')
    log "Docs Typesense GKE : $docs_before -> $docs_after"
    log ""
    log "Etapes :"
    for s in step1 step2 step3 step4 step5; do
        if [ -f "$CHECKPOINT_DIR/$s.done" ]; then
            log "  [OK] $s"
        else
            log "  [..] $s en attente"
        fi
    done
    log ""
    log "Pour reset checkpoints (refaire from scratch) :"
    log "  rm -rf $CHECKPOINT_DIR"
}

# ========== MAIN ==========
preflight
step_2_check
step_1_diff_categories
step_2_ingest
step_3_orphans
step_4_idf
step_5_synonyms
summary
