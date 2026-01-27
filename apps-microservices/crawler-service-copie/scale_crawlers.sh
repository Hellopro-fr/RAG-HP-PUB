#!/bin/bash

# ==============================================================================
# Script to robustly scale the crawler-service with an external Redis.
#
# This script follows a multi-stage process to prevent race conditions:
# 1. Loads connection details for an external Redis from the .env file.
# 2. Authenticates and sets the global concurrent crawl limit in the external Redis.
# 3. Starts and scales the 'crawler-service' replicas.
#
# Usage:
#   ./scale_crawlers.sh [number_of_replicas]
#
# Example:
#   ./scale_crawlers.sh 10  # Scales the service to 10 instances.
#
# If no argument is provided, it defaults to 3 replicas.
#
# IMPORTANT:
# - This script requires `redis-cli` to be installed on the host machine.
# - The .env file must contain REDIS_HOST, REDIS_PORT, and REDIS_SECRET.
# - Before first use, make this script executable:
#   chmod +x apps-microservices/crawler-service/scale_crawlers.sh
# ==============================================================================

# --- PHASE 0: Load Environment and Validate ---
echo "[PHASE 0/4] Loading environment variables and validating tools..."

# Check if redis-cli is installed
if ! command -v redis-cli &> /dev/null
then
    echo "ERROR: redis-cli is not installed. Please install redis-tools and try again."
    exit 1
fi

# The .env file must be in the same directory where docker-compose is run.
if [ ! -f .env ]; then
    echo "ERROR: .env file not found. Please create it and add REDIS_HOST, REDIS_PORT, and REDIS_SECRET."
    exit 1
fi

# Source the .env file to load variables into the environment for this script.
set -o allexport
source .env
set +o allexport

# Validate that all required Redis variables are set.
if [ -z "$REDIS_HOST" ] || [ -z "$REDIS_PORT" ] || [ -z "$REDIS_SECRET" ]; then
    echo "ERROR: One or more required variables (REDIS_HOST, REDIS_PORT, REDIS_SECRET) are not set in the .env file."
    exit 1
fi
echo "Environment loaded and redis-cli found."
echo ""


# --- CONFIGURATION ---

# Default to 3 replicas if no argument is provided.
REPLICAS=${1:-3}

# This value MUST match the MAX_CONCURRENT_CRAWLS value set for the
# crawler-service in the docker compose.yaml file.
CRAWLS_PER_INSTANCE=1

# Calculate the global maximum based on the replica count.
GLOBAL_MAX=$((REPLICAS * CRAWLS_PER_INSTANCE))

# --- EXECUTION ---

echo "----------------------------------------------------"
echo "Targeting $REPLICAS crawler-service replicas."
echo "Calculated MAX_GLOBAL_CONCURRENT_CRAWLS = $GLOBAL_MAX"
echo "Connecting to external Redis at $REDIS_HOST:$REDIS_PORT"
echo "----------------------------------------------------"
echo ""

# --- PHASE 1: Wait for Redis to be healthy ---
echo "[PHASE 1/4] Waiting for external Redis to become healthy..."
# This loop will run until `redis-cli ping` returns "PONG".
# It has a timeout of 30 seconds to prevent it from running forever.
counter=0
until redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" -a "$REDIS_SECRET" ping | grep -q "PONG"; do
    if [ $counter -ge 30 ]; then
        echo "ERROR: External Redis did not become healthy after 30 seconds. Check connection details and password. Aborting."
        exit 1
    fi
    echo "Redis not ready or authentication failed, retrying in 1 second..."
    sleep 1
    counter=$((counter+1))
done
echo "External Redis is healthy and authenticated."
echo ""

# --- PHASE 2: Set the central configuration in Redis ---
echo "[PHASE 2/4] Setting central config key in Redis..."
redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" -a "$REDIS_SECRET" SET crawl_jobs:max_global_crawls $GLOBAL_MAX
echo "Set 'crawl_jobs:max_global_crawls' -> '$GLOBAL_MAX'"
echo ""

# --- PHASE 3: Start dependent services (if needed) ---
echo "[PHASE 3/4] Starting reverse-proxy..."
# Ensure the reverse proxy is up. This command is idempotent.
docker compose --profile crawling up -d --no-deps reverse-proxy
echo "Reverse proxy is up."
echo ""

# --- PHASE 4: Scale the application services ---
echo "[PHASE 4/4] Scaling application services..."
# Now that Redis is configured, scale the crawler service.
# The `--no-deps` flag is used to only scale the specified service.
docker compose --profile crawling up -d --no-deps --scale crawler-service=$REPLICAS
echo ""

# --- PHASE 5: Reload Nginx to discover new replicas ---
echo "[PHASE 5/5] Reloading Nginx in reverse-proxy..."
# Nginx needs to be reloaded to re-resolve the 'crawler-service' hostname
# and pick up the new IP addresses of the scaled replicas.
docker compose --profile crawling exec reverse-proxy nginx -s reload
echo "Nginx reloaded."
echo ""

echo "----------------------------------------------------"
echo "Scaling command complete. System is now running with $REPLICAS replicas."
echo "----------------------------------------------------"