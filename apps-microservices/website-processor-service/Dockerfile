# Stage 1: Build Go CLIs
FROM golang:1.24-alpine AS go-builder
WORKDIR /src

# Install system dependencies
RUN apk add --no-cache git

# Build custom go-trafilatura script
# Key Change: Pointing to the new location in libs
COPY libs/common-utils/src/common_utils/cleaner/go-trafilatura /src/go-extractor
WORKDIR /src/go-extractor
RUN go mod tidy
RUN go build -o go-trafilatura-hp main.go

# Stage 2: Final Python Application
FROM python:3.13-slim
WORKDIR /app

# Étape 1: Définir le PYTHONPATH.
# Dit à Python de toujours chercher les modules à partir du dossier /app.
ENV PYTHONPATH=/app
# SERVICE_NAME drives the Redis CLIENT SETNAME prefix from common_utils
# (cache_service_sync). Overridable at runtime via docker-compose env.
ENV SERVICE_NAME=website-processor-service

# Install build-essential which contains g++ and other build tools
# needed for compiling Python packages like faust-cchardet.
# Also install default-jre-headless for boilerpy3
RUN apt-get update && apt-get install -y --no-install-recommends build-essential default-jre-headless && rm -rf /var/lib/apt/lists/*

# Copy binaries from builder stages
COPY --from=go-builder /src/go-extractor/go-trafilatura-hp /usr/local/bin/go-trafilatura-hp

# Ensure binaries are executable
RUN chmod +x /usr/local/bin/go-trafilatura-hp

# Étape 2: Installer les dépendances
# On copie la lib partagée
COPY libs/common-utils /app/libs/common-utils
RUN pip install -e /app/libs/common-utils
# On copie les requirements du service
COPY apps-microservices/website-processor-service/requirements.txt .
RUN pip install -r requirements.txt

# Étape 3: Copier le code source
# On copie le CONTENU du dossier app local directement dans le WORKDIR (/app)
COPY apps-microservices/website-processor-service/app/ /app/website_processor_service

# Étape 4: Définir la commande
# On peut maintenant exécuter le script directement, les imports fonctionneront grâce au PYTHONPATH.
CMD ["python", "-u", "-m", "website_processor_service.main"]