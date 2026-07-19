#!/bin/bash

# verify_archives_in_gcs.sh — generate the GCS-verified crawl-id allowlist
# consumed by crawler-service's archived-leftover reclean sweep (fail-closed:
# without this file the sweep deletes NOTHING).
#
# Lists gs://$GCS_BUCKET/$PREFIX, keeps *.tar.gz blobs of plausible size
# (>= MIN_SIZE_BYTES, .tmp.tar.gz excluded), and atomically writes the sorted
# unique crawl ids (basename minus .tar.gz) to OUT_FILE.
#
# Usage: verify_archives_in_gcs.sh [GCS_BUCKET] [OUT_FILE]
#
# Configuration (env vars, args override):
# GCS_BUCKET:     bucket name (required; falls back to GCS_BUCKET_NAME from ../.env)
# PREFIX:         path under the bucket (default: crawls/)
# OUT_FILE:       output list. MUST be the HOST path of the volume mounted at
#                 /app/archives in the crawler-service container — the container
#                 reads it as settings.ARCHIVED_RECLEAN_VERIFIED_LIST
#                 (/app/archives/verified_in_gcs.list).
# MIN_SIZE_BYTES: minimum blob size to trust (default: 1024 — a sub-KB tar is garbage)
# INTERSECT_FILE: optional file of ids (one per line); when set, only ids present
#                 in BOTH the GCS listing and this file are emitted (e.g. the BO
#                 est_archiver=1 id list).
DEFAULT_OUT_FILE="$(dirname "$0")/../apps-microservices/crawler-service/crawler_archives/verified_in_gcs.list"
PREFIX="${PREFIX:-crawls/}"
MIN_SIZE_BYTES="${MIN_SIZE_BYTES:-1024}"

# Load .env from parent directory
ENV_FILE="$(dirname "$0")/../.env"
if [ -f "$ENV_FILE" ]; then
    # Export variables from .env so they are available
    set -a
    source "$ENV_FILE"
    set +a
fi

GCS_BUCKET="${1:-${GCS_BUCKET:-$GCS_BUCKET_NAME}}"
OUT_FILE="${2:-${OUT_FILE:-$DEFAULT_OUT_FILE}}"

if [ -z "$GCS_BUCKET" ]; then
    echo "ERROR: GCS_BUCKET is not set. Usage: $0 <GCS_BUCKET> [OUT_FILE]"
    exit 1
fi

echo "Listing gs://$GCS_BUCKET/$PREFIX ..."
if ! listing=$(gcloud storage ls -l "gs://$GCS_BUCKET/$PREFIX"); then
    echo "ERROR: gcloud listing failed. Existing $OUT_FILE left untouched."
    exit 1
fi

listed_count=$(printf '%s\n' "$listing" | grep -c '\.tar\.gz$')

# Lines: "<size>  <date>  gs://bucket/prefix/{id}.tar.gz" (+ a TOTAL: footer).
kept_ids=$(printf '%s\n' "$listing" | awk -v min="$MIN_SIZE_BYTES" '
    $3 ~ /^gs:\/\// && $3 ~ /\.tar\.gz$/ && $3 !~ /\.tmp\.tar\.gz$/ && $1 + 0 >= min {
        n = split($3, parts, "/")
        id = parts[n]
        sub(/\.tar\.gz$/, "", id)
        print id
    }' | sort -u)
kept_count=$(printf '%s' "$kept_ids" | grep -c '.')

final_ids="$kept_ids"
intersect_count="$kept_count"
if [ -n "$INTERSECT_FILE" ]; then
    if [ ! -f "$INTERSECT_FILE" ]; then
        echo "ERROR: INTERSECT_FILE '$INTERSECT_FILE' not found. Existing $OUT_FILE left untouched."
        exit 1
    fi
    final_ids=$(comm -12 <(printf '%s\n' "$kept_ids") <(sort -u "$INTERSECT_FILE"))
    intersect_count=$(printf '%s' "$final_ids" | grep -c '.')
fi

if [ -z "$final_ids" ]; then
    echo "ERROR: verified id set is empty — refusing to clobber $OUT_FILE with an empty list."
    exit 1
fi

printf '%s\n' "$final_ids" > "$OUT_FILE.tmp"
mv -f "$OUT_FILE.tmp" "$OUT_FILE"

echo "Listed:          $listed_count tar.gz blob(s)"
echo "Kept:            $kept_count (size >= $MIN_SIZE_BYTES, non-.tmp)"
echo "After intersect: $intersect_count"
echo "Output:          $OUT_FILE"
