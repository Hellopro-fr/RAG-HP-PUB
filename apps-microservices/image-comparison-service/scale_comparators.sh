#!/bin/bash
# ==============================================================================
# Script to scale the image-comparison-service.
# Usage: ./scale_comparators.sh [number_of_replicas]
# ==============================================================================

REPLICAS=${1:-1}

echo "[INFO] Scaling image-comparison-service to $REPLICAS replicas..."

# 1. Scale the service using Docker Compose
docker compose --profile crawling up -d --no-deps --scale image-comparison-service=$REPLICAS

echo "[INFO] Reloading Reverse Proxy Nginx..."
# 2. Reload Nginx to discover new replicas
docker compose --profile crawling exec reverse-proxy nginx -s reload

echo "[SUCCESS] Scaled to $REPLICAS replicas."