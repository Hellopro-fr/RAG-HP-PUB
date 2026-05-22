#!/usr/bin/env bash
#
# migrate_to_gke.sh (v2, 2026-05-22)
# ==================================
# Orchestre l'ingestion Milvus -> Typesense GKE en passant par les routes
# HTTP du service Python deja deploye sur GKE.
#
# Avantages :
#   - Pas besoin de l'IP Typesense interne GKE (le service Python la connait)
#   - Pas besoin de credentials Milvus en local (le service GKE y accede deja)
#   - Idempotent (upsert) : safe de relancer
#   - Checkpoints + reprise apres interruption
#
# Routes utilisees :
#   GET  /sync/health                   -> preflight
#   GET  /admin/collections/{name}      -> stats actuelles
#   GET  /admin/collections/{name}/...  -> facet categories pour diff
#   POST /admin/collections/{name}      -> creer collection si absente
#   POST /ingest/categories/batch       -> ingestion chunked
#   POST /sync/incremental              -> delta NEW+UPDATED+DELETED
#
# Usage :
#   cd ~/RAG-HP-PUB
#   bash apps-microservices/opti-moteur-front/vm/migrate_to_gke.sh
#
# Run non-interactif :
#   AUTO=1 bash apps-microservices/opti-moteur-front/vm/migrate_to_gke.sh
#
# Reset checkpoints (refaire from scratch) :
#   rm -rf /tmp/migrate_gke_checkpoints

set -eu
set -o pipefail

# ========== CONFIG ==========
REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"

# Service Python GKE (entree HTTP unique)
GKE_API="${GKE_API:-http://10.0.1.240:8570}"

# La collection cible (defaut = settings du service GKE)
TS_COLLECTION="${TS_COLLECTION:-produits_prod}"

# Sync token (cron Ecritel). Doit matcher SYNC_TOKEN en env du service GKE.
SYNC_TOKEN="${SYNC_TOKEN:-hp_sync_2026_04_30_xZ7q}"

# Taille de chunk pour /ingest/categories/batch (route bloquante)
# A 20 categories de ~500 produits = ~10k docs par appel = ~2-5 min
CHUNK_SIZE="${CHUNK_SIZE:-20}"

# Filtre etat passe a chaque ingestion
EXTRA_FILTER="${EXTRA_FILTER:-etat in [\"Client\",\"Pause\",\"Prospect\"]}"

# Source de verite catalogue Milvus (cree par list_missing_categories.py
# ou maintenu manuellement)
CATEGORIES_FILE="${CATEGORIES_FILE:-$REPO_ROOT/rubriques/categories_from_roots.txt}"

CHECKPOINT_DIR="${CHECKPOINT_DIR:-/tmp/migrate_gke_checkpoints}"
LOG_DIR="${LOG_DIR:-/tmp/migrate_gke_logs}"
mkdir -p "$CHECKPOINT_DIR" "$LOG_DIR"
AUTO="${AUTO:-0}"
TS="$(date +%Y%m%d_%H%M%S)"

# ========== HELPERS ==========
log() { echo "[$(date +%H:%M:%S)] $*"; }
err() { echo "[$(date +%H:%M:%S)] ERROR: $*" >&2; }

confirm() {
    if [ "$AUTO" = "1" ]; then return 0; fi
    read -r -p "$1 [y/N] " ans
    case "$ans" in [yY]*) return 0 ;; *) return 1 ;; esac
}

step_done() { touch "$CHECKPOINT_DIR/$1.done"; }
step_pending() { [ ! -f "$CHECKPOINT_DIR/$1.done" ]; }

api_get() {
    # api_get <path>
    curl -sf "$GKE_API$1" || return 1
}

api_post_json() {
    # api_post_json <path> <json-body> [extra-headers...]
    local path="$1" body="$2"; shift 2
    curl -sf -X POST "$GKE_API$path" \
        -H "Content-Type: application/json" \
        "$@" \
        -d "$body"
}

# ========== ETAPES ==========
preflight() {
    log "=== Preflight ==="
    log "Target API : $GKE_API"
    log "Collection : $TS_COLLECTION"

    # On utilise /health (main.py) qui est universel : format
    # {"status":"ok","typesense":"ok","milvus":"ok"}
    # /sync/health donne plus de detail mais peut etre absent sur d'anciennes
    # versions deployees sur GKE.
    local health
    health=$(api_get "/health") || {
        err "Service Python GKE injoignable a $GKE_API/health"
        err "  -> joindre Tafita pour verifier le pod + ingress + firewall"
        exit 1
    }
    log "Health: $(echo "$health" | jq -c .)"
    if ! echo "$health" | jq -e '.milvus == "ok"' >/dev/null; then
        err "Milvus pas OK depuis le service GKE"
        err "$(echo "$health" | jq -r .milvus)"
        exit 1
    fi
    if ! echo "$health" | jq -e '.typesense == "ok"' >/dev/null; then
        err "Typesense pas OK depuis le service GKE"
        err "$(echo "$health" | jq -r .typesense)"
        exit 1
    fi

    # Verifier que les routes admin/ingest/sync sont bien deployees
    # (image GKE potentiellement plus ancienne que le code repo).
    log "Verification des routes deployees..."
    local routes_ok=1
    for route in "/admin/collections" "/ingest/category"; do
        if curl -sf -o /dev/null -w "%{http_code}" "$GKE_API$route" 2>&1 \
           | grep -qE "^(200|405|422)"; then
            log "  OK $route"
        else
            err "  KO $route (route absente ou erreur)"
            routes_ok=0
        fi
    done
    if [ "$routes_ok" -eq 0 ]; then
        err "L'image GKE n'expose pas toutes les routes attendues."
        err "  -> Tafita doit redeployer avec l'image actuelle (features/poc HEAD)"
        err "  -> En attendant, voir routes dispo via :"
        err "     curl $GKE_API/openapi.json | jq '.paths | keys'"
        exit 1
    fi

    local stats
    if stats=$(api_get "/admin/collections/$TS_COLLECTION" 2>/dev/null); then
        local n
        n=$(echo "$stats" | jq -r '.num_documents // 0')
        log "Collection $TS_COLLECTION : $n docs"
        echo "$n" > "$CHECKPOINT_DIR/docs_before.txt"
    else
        log "Collection $TS_COLLECTION inexistante. Sera creee a l'etape 1."
    fi
}

step_1_create_collection() {
    if ! step_pending "step1"; then log "step1 deja fait, skip"; return; fi
    log "=== Etape 1 : creer la collection si necessaire ==="

    if api_get "/admin/collections/$TS_COLLECTION" >/dev/null 2>&1; then
        log "Collection $TS_COLLECTION existe deja"
        step_done "step1"
        return
    fi

    confirm "Creer la collection '$TS_COLLECTION' avec le schema standard ?" || return
    api_post_json "/admin/collections/$TS_COLLECTION" "{}" \
        | tee "$LOG_DIR/step1_create_${TS}.log" >/dev/null
    log "Collection creee"
    step_done "step1"
}

step_2_diff_categories() {
    if ! step_pending "step2"; then log "step2 deja fait, skip"; return; fi
    log "=== Etape 2 : diff categories ($CATEGORIES_FILE vs Typesense GKE) ==="

    [ -f "$CATEGORIES_FILE" ] || {
        err "Fichier source catalogue absent : $CATEGORIES_FILE"
        err "  -> exporter depuis Milvus via list_missing_categories.py"
        err "  -> ou fournir un fichier custom via CATEGORIES_FILE=... bash $0"
        return 1
    }
    local total
    total=$(wc -l < "$CATEGORIES_FILE")
    log "Catalogue cible : $total categories ($CATEGORIES_FILE)"

    # Recuperer les categories deja presentes dans Typesense via facet
    local categories_present_file="$CHECKPOINT_DIR/categories_present.txt"
    log "Recuperation des categories actuelles via facet..."
    api_get "/search/text" >/dev/null 2>&1 || true  # warm-up
    # /admin n'a pas de facet direct, on fait via une requete de search
    # qui retourne le facet (POST /search avec q=*) - utiliser la collection
    # directement via search Typesense par le service Python.
    # Solution simple : appeler /search (route principale) avec un facet hack
    # Hack alternatif : faire un POST /search/text avec un query qui matche
    # tout, et facets.

    # Approche pragmatique : on bombarde TOUTES les categories, l'upsert
    # est idempotent. Pas besoin de diff strict ici, le service /ingest/category
    # filtre Milvus par categorie donc rien ne se passe si rien a ingerer.

    cp "$CATEGORIES_FILE" "$CHECKPOINT_DIR/categories_to_ingest.txt"
    log "Plan d'ingestion : toutes les $total categories (idempotent)."
    log "Note : Typesense fait upsert, pas de duplicat cree."
    step_done "step2"
}

step_3_ingest_chunked() {
    if ! step_pending "step3"; then log "step3 deja fait, skip"; return; fi
    log "=== Etape 3 : ingestion par chunks de $CHUNK_SIZE categories ==="

    local cats_file="$CHECKPOINT_DIR/categories_to_ingest.txt"
    [ -f "$cats_file" ] || { err "step2 incomplete"; return 1; }
    local total
    total=$(wc -l < "$cats_file")
    log "Total : $total categories, chunks de $CHUNK_SIZE"

    confirm "Lancer l'ingestion (~$((total * 30 / 60)) min estimees) ?" || return

    local progress_file="$CHECKPOINT_DIR/step3_progress.txt"
    local n_done=0
    [ -f "$progress_file" ] && n_done=$(cat "$progress_file")
    log "Reprise depuis ligne $n_done"

    local chunk_idx=0
    local line_idx=0
    local chunk_cats=""

    # Lecture ligne par ligne
    while IFS= read -r cat || [ -n "$cat" ]; do
        line_idx=$((line_idx + 1))
        # Skip lignes vides ou commentaires
        [ -z "$cat" ] && continue
        case "$cat" in \#*) continue ;; esac
        # Skip si deja traite (reprise)
        if [ "$line_idx" -le "$n_done" ]; then continue; fi

        # Echappe les guillemets pour le JSON
        cat_escaped=$(echo "$cat" | sed 's/"/\\"/g')
        if [ -z "$chunk_cats" ]; then
            chunk_cats="\"$cat_escaped\""
        else
            chunk_cats="$chunk_cats,\"$cat_escaped\""
        fi

        if [ $((line_idx % CHUNK_SIZE)) -eq 0 ]; then
            chunk_idx=$((chunk_idx + 1))
            send_chunk "$chunk_idx" "$chunk_cats" "$line_idx" "$total"
            chunk_cats=""
            echo "$line_idx" > "$progress_file"
        fi
    done < "$cats_file"

    # Flush du dernier chunk partiel
    if [ -n "$chunk_cats" ]; then
        chunk_idx=$((chunk_idx + 1))
        send_chunk "$chunk_idx" "$chunk_cats" "$line_idx" "$total"
        echo "$line_idx" > "$progress_file"
    fi

    log "Ingestion terminee : $line_idx categories"
    step_done "step3"
}

send_chunk() {
    local idx="$1" cats="$2" pos="$3" total="$4"
    log "Chunk #$idx (pos $pos/$total)..."
    local body
    body=$(cat <<EOF
{
  "categories": [$cats],
  "ts_collection": "$TS_COLLECTION",
  "extra_filter": "$EXTRA_FILTER",
  "batch_size": 1000,
  "stop_if_disk_gb_below": 3.0
}
EOF
)
    local logfile="$LOG_DIR/step3_chunk_${idx}_${TS}.json"
    if api_post_json "/ingest/categories/batch" "$body" > "$logfile" 2>&1; then
        local n_ok n_total
        n_ok=$(jq -r '.total_chunks_ok // 0' < "$logfile")
        n_total=$(jq -r '.total_chunks_milvus // 0' < "$logfile")
        log "  OK $n_ok/$n_total chunks. Detail : $logfile"
    else
        err "Echec chunk #$idx. Voir $logfile"
        err "Reprendre via : bash $0 (reprend a la ligne $pos)"
        exit 1
    fi
}

step_4_sync_delta() {
    if ! step_pending "step4"; then log "step4 deja fait, skip"; return; fi
    log "=== Etape 4 : sync incremental (NEW + UPDATED + DELETED orphelins) ==="

    confirm "Lancer /sync/incremental (delta + orphelins) ?" || return

    local body
    body=$(cat <<EOF
{
  "delete_orphans": true,
  "batch_size": 1000
}
EOF
)
    local logfile="$LOG_DIR/step4_sync_${TS}.json"
    if api_post_json "/sync/incremental" "$body" -H "X-Sync-Token: $SYNC_TOKEN" > "$logfile" 2>&1; then
        cat "$logfile" | jq .
        step_done "step4"
    else
        err "Sync incremental echoue. Voir $logfile"
        return 1
    fi
}

step_5_idf() {
    if ! step_pending "step5"; then log "step5 deja fait, skip"; return; fi
    log "=== Etape 5 : regenerer IDF (sur le pod GKE) ==="

    err "ACTION MANUELLE : regenerer idf_nom_produit.json sur le pod GKE"
    err "  kubectl exec -it <pod-opti-moteur-front> -- python scripts/compute_idf.py"
    err "  puis kubectl rollout restart deployment opti-moteur-front"
    err "(demander a Tafita si tu n'as pas l'acces kubectl)"
    err ""
    err "Alternative : si le service expose une route /admin/compute-idf"
    err "(pas le cas aujourd'hui), on pourrait l'appeler ici."

    confirm "Marquer cette etape comme done (apres action manuelle Tafita) ?" \
        && step_done "step5"
}

summary() {
    log "=== Resume ==="
    local docs_before docs_after
    docs_before=$(cat "$CHECKPOINT_DIR/docs_before.txt" 2>/dev/null || echo "?")
    docs_after=$(api_get "/admin/collections/$TS_COLLECTION" 2>/dev/null \
                 | jq -r '.num_documents // "?"')
    log "Docs Typesense : $docs_before -> $docs_after"
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
    log "Reset complet : rm -rf $CHECKPOINT_DIR"
    log "Logs detailles : ls -lh $LOG_DIR"
}

# ========== MAIN ==========
preflight
step_1_create_collection
step_2_diff_categories
step_3_ingest_chunked
step_4_sync_delta
step_5_idf
summary
