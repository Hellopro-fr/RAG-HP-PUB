# Stage 1: Build the Node.js/TypeScript crawler
FROM node:22-slim AS builder

WORKDIR /app/crawler

# Copy package files and install dependencies. This will download the playwright npm package.
COPY apps-microservices/crawler-service/crawler/package*.json ./
RUN npm install

# Copy the rest of the crawler source code
COPY apps-microservices/crawler-service/crawler/ ./

# Build the TypeScript project into JavaScript
RUN npm run build


# Stage 2: Create the final Python application image using the official Playwright image
# This image contains the browser binaries and all OS dependencies for a specific Playwright version.
FROM mcr.microsoft.com/playwright/python:v1.56.1-noble

WORKDIR /app

ENV PYTHONPATH=/app

# Install the Node.js runtime, required for our Python app to call the Node.js crawler.
RUN apt-get update && apt-get install -y nodejs npm --no-install-recommends && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
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

# Command to run the FastAPI server
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8503"]