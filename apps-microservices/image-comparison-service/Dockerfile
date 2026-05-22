# Stage 1: Base Image
FROM python:3.11-slim

WORKDIR /app

# SERVICE_NAME drives the Redis CLIENT SETNAME prefix from common_utils
# (cache_service). Overridable at runtime via docker-compose env.
ENV SERVICE_NAME=image-comparison-service

# Install system dependencies required for OpenCV and image processing
# libgl1: Replacement for deprecated libgl1-mesa-glx
# libglib2.0-0: Required for some image parsing
RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Install shared lib common-utils (Redis pool, etc.)
COPY libs/common-utils /app/libs/common-utils
RUN pip install -e /app/libs/common-utils

# Install Python dependencies
COPY apps-microservices/image-comparison-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY apps-microservices/image-comparison-service/app ./app
COPY apps-microservices/image-comparison-service/main.py .

# Expose the port
EXPOSE 8504

# Run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8504"]