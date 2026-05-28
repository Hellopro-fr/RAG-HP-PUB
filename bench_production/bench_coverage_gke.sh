#!/usr/bin/env bash
#
# bench_coverage_gke.sh
# =====================
# Bench couverture sur 150 mots-cles stratifies (keywords_coverage_v1.csv)
# contre le service Python GKE (10.0.1.240:8570).
#
# Output :
#   - bench_results/coverage_<TS>.csv : 1 ligne par mot-cle avec top-3 + latency
#   - bench_results/coverage_<TS>_summary.txt : stats par bucket
#
# Usage :
#   cd ~/RAG-HP-PUB
#   bash bench_production/bench_coverage_gke.sh
#
#   # Override URL si besoin (par defaut GKE direct)
#   GKE_URL=https://api.hellopro.eu/optimoteur-service \
#     bash bench_production/bench_coverage_gke.sh
#
# Pre-requis : jq + curl (deja sur la VM)

set -eu

# ========== CONFIG ==========
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
GKE_URL="${GKE_URL:-http://10.0.1.240:8570}"
KEYWORDS_CSV="${KEYWORDS_CSV:-$REPO_ROOT/bench_production/keywords_coverage_v1.csv}"
OUT_DIR="${OUT_DIR:-$REPO_ROOT/bench_production/bench_results}"
TS="$(date +%Y%m%d_%H%M%S)"
OUT_CSV="$OUT_DIR/coverage_${TS}.csv"
OUT_SUMMARY="$OUT_DIR/coverage_${TS}_summary.txt"

mkdir -p "$OUT_DIR"

# ========== HELPERS ==========
log() { echo "[$(date +%H:%M:%S)] $*"; }
err() { echo "[$(date +%H:%M:%S)] ERROR: $*" >&2; }

# ========== PREFLIGHT ==========
log "=== Preflight ==="
log "Target API : $GKE_URL"
log "Keywords   : $KEYWORDS_CSV"
log "Output CSV : $OUT_CSV"

if ! curl -sf "$GKE_URL/health" -o /dev/null; then
    err "Service injoignable a $GKE_URL/health"
    exit 1
fi
log "Health OK"

if [ ! -f "$KEYWORDS_CSV" ]; then
    err "CSV mots-cles introuvable : $KEYWORDS_CSV"
    exit 1
fi

# ========== HEADER CSV ==========
echo "mot_cle,bucket,top1,top2,top3,latency_ms,http_status,nb_results" > "$OUT_CSV"

# ========== LECTURE CSV + BENCH ==========
# Format CSV input : mot_cle,bucket,nb_recherches,avg_results,notes
# On skip la 1ere ligne (header)

total=0
ok=0
errors=0
declare -A bucket_count
declare -A bucket_ok
declare -A bucket_lat_total

# Lecture ligne par ligne (skip header)
{
    read -r header  # skip header
    while IFS=, read -r mot_cle bucket nb_recherches avg_results notes; do
        # Skip lignes vides ou commentaires
        [ -z "$mot_cle" ] && continue
        case "$mot_cle" in \#*) continue ;; esac

        total=$((total + 1))
        bucket_count["$bucket"]=$((${bucket_count["$bucket"]:-0} + 1))

        # Echapper les " et \ pour JSON
        query_escaped=$(echo "$mot_cle" | sed 's/\\/\\\\/g; s/"/\\"/g')

        # Request avec mesure latence
        body="{\"query\":\"$query_escaped\",\"top_k\":3}"
        tmpfile=$(mktemp)
        t_start=$(date +%s%N)
        http_code=$(curl -s -o "$tmpfile" -w "%{http_code}" \
                    --max-time 15 \
                    -X POST "$GKE_URL/search/text" \
                    -H "Content-Type: application/json" \
                    -d "$body" 2>/dev/null || echo "000")
        t_end=$(date +%s%N)
        latency_ms=$(( (t_end - t_start) / 1000000 ))

        if [ "$http_code" = "200" ]; then
            ok=$((ok + 1))
            bucket_ok["$bucket"]=$((${bucket_ok["$bucket"]:-0} + 1))
            bucket_lat_total["$bucket"]=$((${bucket_lat_total["$bucket"]:-0} + latency_ms))

            nb_results=$(jq -r '.results | length // 0' < "$tmpfile" 2>/dev/null || echo 0)
            top1=$(jq -r '.results[0].nom_produit // ""' < "$tmpfile" 2>/dev/null \
                   | sed 's/,/;/g' | tr -d '\n' | tr -d '\r')
            top2=$(jq -r '.results[1].nom_produit // ""' < "$tmpfile" 2>/dev/null \
                   | sed 's/,/;/g' | tr -d '\n' | tr -d '\r')
            top3=$(jq -r '.results[2].nom_produit // ""' < "$tmpfile" 2>/dev/null \
                   | sed 's/,/;/g' | tr -d '\n' | tr -d '\r')
            # Tronquer top-1 a 100 chars pour log lisible
            top1_short=$(echo "$top1" | cut -c1-80)
            log "[$total] $mot_cle ($bucket, ${latency_ms}ms, $nb_results res) -> $top1_short"
        else
            errors=$((errors + 1))
            top1=""; top2=""; top3=""; nb_results=0
            err "[$total] $mot_cle ($bucket) HTTP=$http_code"
        fi

        # Echappement final CSV
        echo "\"$mot_cle\",\"$bucket\",\"$top1\",\"$top2\",\"$top3\",$latency_ms,$http_code,$nb_results" >> "$OUT_CSV"

        rm -f "$tmpfile"
    done
} < "$KEYWORDS_CSV"

# ========== SUMMARY ==========
log "=== Resume ==="
{
    echo "Bench coverage GKE - $TS"
    echo "Target : $GKE_URL"
    echo ""
    echo "Total : $total mots-cles"
    echo "OK    : $ok"
    echo "Errors: $errors"
    echo ""
    echo "Par bucket :"
    printf "  %-20s %6s %6s %10s\n" "Bucket" "Total" "OK" "Lat moyenne"
    for b in "${!bucket_count[@]}"; do
        cnt=${bucket_count[$b]}
        bok=${bucket_ok[$b]:-0}
        blat=${bucket_lat_total[$b]:-0}
        avg=$(( bok > 0 ? blat / bok : 0 ))
        printf "  %-20s %6s %6s %8s ms\n" "$b" "$cnt" "$bok" "$avg"
    done
} | tee "$OUT_SUMMARY"

log ""
log "Resultats : $OUT_CSV"
log "Summary   : $OUT_SUMMARY"
log ""
log "Pour analyser le top-1 par bucket :"
log "  awk -F'\",\"' '{print \$2}' $OUT_CSV | sort | uniq -c | sort -rn"
