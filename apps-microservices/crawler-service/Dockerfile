# Stage 1: Build the Node.js/TypeScript crawler
FROM node:22-slim AS builder

WORKDIR /app/crawler

# Copy package files and install dependencies
COPY apps-microservices/crawler-service/crawler/package*.json ./
RUN npm install

# Install Playwright browsers AND their OS dependencies.
# This is the most reliable way to set up the environment.
RUN npx playwright install --with-deps

# Copy the rest of the crawler source code
COPY apps-microservices/crawler-service/crawler/ ./

# Build the TypeScript project into JavaScript
RUN npm run build


# Stage 2: Create the final Python application image using the official Playwright image
FROM mcr.microsoft.com/playwright/python:v1.55.0-noble

WORKDIR /app

ENV PYTHONPATH=/app

# Install the Node.js runtime. The official Playwright Python image does not
# include it, but it's required for our Python app to call the Node.js crawler.
RUN apt-get update && apt-get install -y nodejs npm --no-install-recommends && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY apps-microservices/crawler-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the Python application code
COPY apps-microservices/crawler-service/app ./app
COPY apps-microservices/crawler-service/main.py .

# Copy the compiled crawler and its dependencies from the builder stage
COPY --from=builder /app/crawler/dist ./crawler/dist
COPY --from=builder /app/crawler/node_modules ./crawler/node_modules

# Copy package.json to provide module context ("type": "module") to the Node.js runtime
COPY --from=builder /app/crawler/package.json /app/crawler/package.json
COPY --from=builder /app/crawler/package-lock.json /app/crawler/package-lock.json

# Copy the downloaded Playwright browser binaries from the builder stage to ensure version consistency
COPY --from=builder /root/.cache/ms-playwright /root/.cache/ms-playwright


# Expose the port for the FastAPI application
EXPOSE 8503

# Command to run the FastAPI server
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8503"]