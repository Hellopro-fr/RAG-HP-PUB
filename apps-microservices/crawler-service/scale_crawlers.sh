#!/bin/bash

# ==============================================================================
# Script to scale the crawler-service correctly.
#
# This script automates the calculation of the global concurrent crawl limit
# and stores it in Redis, which acts as the single source of truth for the
# entire cluster.
#
# Usage:
#   ./scale_crawlers.sh [number_of_replicas]
#
# Example:
#   ./scale_crawlers.sh 5  # Scales the service to 5 instances.
#
# If no argument is provided, it defaults to 3 replicas.
#
# IMPORTANT: Before first use, make this script executable:
#   chmod +x apps-microservices/crawler-service/scale_crawlers.sh
# ==============================================================================

# Default to 3 replicas if no argument is provided.
REPLICAS=${1:-3}

# This value MUST match the MAX_CONCURRENT_CRAWLS value set for the
# crawler-service in the docker-compose.yaml file.
CRAWLS_PER_INSTANCE=1

# Calculate the global maximum based on the replica count.
GLOBAL_MAX=$((REPLICAS * CRAWLS_PER_INSTANCE))

echo "----------------------------------------------------"
echo "Scaling crawler-service to $REPLICAS instances..."
echo "Setting central config in Redis: crawl_jobs:max_global_crawls = $GLOBAL_MAX"
echo "----------------------------------------------------"

# Set the authoritative global max value in Redis.
# The `docker-compose exec` command runs `redis-cli` inside the running redis container.
docker compose exec redis redis-cli SET crawl_jobs:max_global_crawls $GLOBAL_MAX

# Bring up the services with the new scale.
# The containers will read the new value from Redis via the /capacity endpoint.
docker compose --profile crawling up -d --scale crawler-service=$REPLICAS

echo "Scaling command complete."