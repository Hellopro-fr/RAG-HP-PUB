#!/bin/bash
# ==============================================================================
# redis_diagnose.sh — Operator-side Redis connection diagnostic.
#
# Mirrors scale_crawlers.sh: loads .env, runs redis-cli against external Redis.
# Use BEFORE applying server-side CONFIG SET + AFTER fix deploys to verify.
#
# Usage:
#   ./redis_diagnose.sh                  # diagnostic only (no writes)
#   ./redis_diagnose.sh --apply-timeout  # also runs CONFIG SET timeout 300
#                                        # + tcp-keepalive 60 + REWRITE
#
# Spec: docs/superpowers/specs/2026-05-21-redis-connection-leak-fix-design.md
# ==============================================================================

set -e

if ! command -v redis-cli &> /dev/null; then
    echo "ERROR: redis-cli not installed. Install redis-tools (or equivalent)."
    exit 1
fi

if [ ! -f .env ]; then
    echo "ERROR: .env not found. Run from the repo root (where docker compose runs)."
    exit 1
fi

set -o allexport
source .env
set +o allexport

if [ -z "$REDIS_HOST" ] || [ -z "$REDIS_PORT" ] || [ -z "$REDIS_SECRET" ]; then
    echo "ERROR: REDIS_HOST / REDIS_PORT / REDIS_SECRET missing in .env."
    exit 1
fi

RCLI=(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" -a "$REDIS_SECRET" --no-auth-warning)

echo "===================================================="
echo " Redis @ $REDIS_HOST:$REDIS_PORT"
echo "===================================================="

echo ""
echo "=== Server config ==="
"${RCLI[@]}" CONFIG GET maxclients
"${RCLI[@]}" CONFIG GET timeout
"${RCLI[@]}" CONFIG GET tcp-keepalive
"${RCLI[@]}" CONFIG GET maxmemory

echo ""
echo "=== Connection stats ==="
"${RCLI[@]}" INFO clients

echo ""
echo "=== Top 20 clients by addr ==="
"${RCLI[@]}" CLIENT LIST | awk '{print $2, $4}' | sort | uniq -c | sort -rn | head -20

echo ""
echo "=== Client name distribution ==="
"${RCLI[@]}" CLIENT LIST | grep -oP 'name=\K[^ ]+' | sort | uniq -c | sort -rn | head -20

if [ "$1" = "--apply-timeout" ]; then
    echo ""
    echo "=== Applying server-side idle reap ==="
    "${RCLI[@]}" CONFIG SET timeout 300
    "${RCLI[@]}" CONFIG SET tcp-keepalive 60
    "${RCLI[@]}" CONFIG REWRITE
    echo "Done. New conns will be reaped after 300s idle."
fi
