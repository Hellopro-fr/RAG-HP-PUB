FROM python:3.11-slim

WORKDIR /app

# Définir le PYTHONPATH
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
# SERVICE_NAME drives the Redis CLIENT SETNAME prefix from common_utils
# (cache_service_sync). Overridable at runtime via docker-compose env.
ENV SERVICE_NAME=image-download-service

# Install system dependencies for Pillow
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libjpeg-dev \
    zlib1g-dev \
    libvips-dev \
    libwebp-dev \
    librsvg2-dev \
    && rm -rf /var/lib/apt/lists/*

# Installer la lib partagée common-utils
COPY libs/common-utils /app/libs/common-utils
RUN pip install -e /app/libs/common-utils

# Installer les dépendances du service
COPY apps-microservices/image-download-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copier le code source
COPY apps-microservices/image-download-service/app/ /app/image_download_service

# Expose port
EXPOSE 8505

CMD ["uvicorn", "image_download_service.main:app", "--host", "0.0.0.0", "--port", "8505"]
