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


# Stage 2: Create the final Python application image
FROM python:3.11-slim

WORKDIR /app

ENV PYTHONPATH=/app

# Install Node.js runtime and procps (for `ps` command required by crawlee/playwright)
RUN apt-get update && apt-get install -y nodejs npm procps --no-install-recommends && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY apps-microservices/crawler-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the Python application code
COPY apps-microservices/crawler-service/app ./app
COPY apps-microservices/crawler-service/main.py .

# Copy the compiled crawler and its dependencies from the builder stage
COPY --from=builder /app/crawler/dist ./crawler/dist
COPY --from=builder /app/crawler/node_modules ./crawler/node_modules

# Copy the downloaded Playwright browser binaries from the builder stage
COPY --from=builder /root/.cache/ms-playwright /root/.cache/ms-playwright


# Expose the port for the FastAPI application
EXPOSE 8503

# Command to run the FastAPI server
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8503"]