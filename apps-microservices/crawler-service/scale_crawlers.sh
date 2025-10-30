#!/bin/bash

# ==============================================================================
# Script to robustly scale the crawler-service.
#
# This script follows a multi-stage process to prevent race conditions:
# 1. Starts the 'redis' service and waits for it to be healthy.
# 2. Sets the global concurrent crawl limit in Redis, which acts as the
#    single source of truth for the entire cluster.
# 3. Starts and scales the 'crawler-service' replicas, which will now
#    read the correct configuration on startup.
#
# Usage:
#   ./scale_crawlers.sh [number_of_replicas]
#
# Example:
#   ./scale_crawlers.sh 10  # Scales the service to 10 instances.
#
# If no argument is provided, it defaults to 3 replicas.
#
# IMPORTANT: Before first use, make this script executable:
#   chmod +x apps-microservices/crawler-service/scale_crawlers.sh
# ==============================================================================

# --- CONFIGURATION ---

# Default to 3 replicas if no argument is provided.
REPLICAS=${1:-3}

# This value MUST match the MAX_CONCURRENT_CRAWLS value set for the
# crawler-service in the docker-compose.yaml file.
CRAWLS_PER_INSTANCE=1

# Calculate the global maximum based on the replica count.
GLOBAL_MAX=$((REPLICAS * CRAWLS_PER_INSTANCE))

# --- EXECUTION ---

echo "----------------------------------------------------"
echo "Targeting $REPLICAS crawler-service replicas."
echo "Calculated MAX_GLOBAL_CONCURRENT_CRAWLS = $GLOBAL_MAX"
echo "----------------------------------------------------"
echo ""

# --- PHASE 1: Ensure Redis is running ---
echo "[PHASE 1/4] Starting Redis dependency..."
# The '--no-deps' flag ensures we only start Redis itself.
docker-compose --profile crawling up -d --no-deps redis
echo "Redis container is up."
echo ""

# --- PHASE 2: Wait for Redis to be healthy ---
echo "[PHASE 2/4] Waiting for Redis to become healthy..."
# This loop will run until `redis-cli ping` returns "PONG".
# It has a timeout of 30 seconds to prevent it from running forever.
counter=0
until docker-compose exec redis redis-cli ping | grep -q "PONG"; do
    if [ $counter -ge 30 ]; then
        echo "ERROR: Redis did not become healthy after 30 seconds. Aborting."
        exit 1
    fi
    echo "Redis not ready yet, waiting 1 second..."
    sleep 1
    counter=$((counter+1))
done
echo "Redis is healthy and ready for commands."
echo ""

# --- PHASE 3: Set the central configuration in Redis ---
echo "[PHASE 3/4] Setting central config key in Redis..."
docker-compose exec redis redis-cli SET crawl_jobs:max_global_crawls $GLOBAL_MAX
echo "Set 'crawl_jobs:max_global_crawls' -> '$GLOBAL_MAX'"
echo ""

# --- PHASE 4: Scale the application services ---
echo "[PHASE 4/4] Scaling application services..."
# Now that Redis is configured, start the crawler and proxy services.
# The `--no-deps` flag prevents it from trying to restart Redis.
# The `up` command is idempotent and will create/start the reverse-proxy if needed.
docker-compose --profile crawling up -d --no-deps --scale crawler-service=$REPLICAS
echo ""
echo "----------------------------------------------------"
echo "Scaling command complete. System is now running with $REPLICAS replicas."
echo "----------------------------------------------------"