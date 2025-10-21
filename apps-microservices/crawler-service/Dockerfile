# Stage 1: Build the Node.js/TypeScript crawler
FROM node:22-slim AS builder

WORKDIR /app/crawler

# Copy package files and install dependencies
COPY apps-microservices/crawler-service/crawler/package*.json ./
RUN npm install

# Install Playwright's OS dependencies using its bundled command.
# This is crucial for running headless browsers in a minimal environment like slim images.
RUN npx playwright install-deps

# Copy the rest of the crawler source code
COPY apps-microservices/crawler-service/crawler/ ./

# Build the TypeScript project into JavaScript
RUN npm run build


# Stage 2: Create the final Python application image
FROM python:3.11-slim

WORKDIR /app

ENV PYTHONPATH=/app

# Install Node.js runtime, which is required to execute the crawler subprocess
RUN apt-get update && apt-get install -y nodejs npm --no-install-recommends && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY apps-microservices/crawler-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the Python application code
COPY apps-microservices/crawler-service/app ./app
COPY apps-microservices/crawler-service/main.py .

# Copy the compiled crawler and its dependencies from the builder stage
# The source path is relative to the builder's WORKDIR
COPY --from=builder /app/crawler/dist ./crawler/dist
COPY --from=builder /app/crawler/node_modules ./crawler/node_modules

# Expose the port for the FastAPI application
EXPOSE 8503

# Command to run the FastAPI server
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8503"]