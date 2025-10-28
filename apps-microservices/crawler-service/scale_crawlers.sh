#!/bin/bash

# ==============================================================================
# Script to scale the crawler-service correctly.
#
# This script automates the calculation of MAX_GLOBAL_CONCURRENT_CRAWLS
# based on the desired number of replicas, preventing configuration errors.
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
echo "Setting MAX_GLOBAL_CONCURRENT_CRAWLS = $GLOBAL_MAX"
echo "----------------------------------------------------"

# Export the variable so Docker Compose can use it, then run the command.
export MAX_GLOBAL_CONCURRENT_CRAWLS=$GLOBAL_MAX

docker compose --profile crawling up -d --scale crawler-service=$REPLICAS

echo "Scaling command complete."