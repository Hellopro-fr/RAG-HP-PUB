# Stage 1: Build the Node.js/TypeScript crawler
FROM node:22-slim AS builder

WORKDIR /app/crawler

# Copy package files and install dependencies.
COPY apps-microservices/crawler-service/crawler/package*.json ./
RUN npm install

# Copy the rest of the crawler source code
COPY apps-microservices/crawler-service/crawler/ ./

# Build the TypeScript project into JavaScript
RUN npm run build

# Download Camoufox stealth browser binary (~200MB, baked into image)
RUN npx camoufox-js fetch


# Stage 2: Create the final application image using the official Playwright image
# This image contains Node.js, the browser binaries, and all OS dependencies for Playwright v1.56.1.
FROM mcr.microsoft.com/playwright:v1.56.1-noble

WORKDIR /app

ENV PYTHONPATH=/app

# Install Python, pip, and venv module.
RUN apt-get update && apt-get install -y python3 python3-pip python3-venv --no-install-recommends && rm -rf /var/lib/apt/lists/*

# Create and activate a virtual environment
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# We copy the shared lib
COPY libs/common-utils /app/libs/common-utils
RUN pip install -e /app/libs/common-utils

# Install Python dependencies into the virtual environment
COPY apps-microservices/crawler-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the Python application code
COPY apps-microservices/crawler-service/app ./app
COPY apps-microservices/crawler-service/main.py .

# Copy the compiled crawler, its dependencies, and its config from the builder stage
COPY --from=builder /app/crawler/dist ./crawler/dist
COPY --from=builder /app/crawler/node_modules ./crawler/node_modules
COPY --from=builder /app/crawler/package.json /app/crawler/package.json
COPY --from=builder /app/crawler/package-lock.json /app/crawler/package-lock.json

# Expose the port for the FastAPI application
EXPOSE 8503

# Set Node.js heap size to ~83% of Docker container limit (6GB)
# Must be LESS than container memory to leave room for browser processes and prevent OOM-kill
ENV NODE_OPTIONS="--max-old-space-size=5000 --expose-gc"

# Command to run the FastAPI server. Uvicorn will be found in the venv's PATH.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8503"]