# Stage 1: Build the Node.js/TypeScript crawler
FROM node:22-slim AS builder

WORKDIR /app/crawler

# Copy package files and install dependencies
COPY apps-microservices/crawler-service/crawler/package*.json ./
RUN npm install

# Copy the rest of the crawler source code
COPY apps-microservices/crawler-service/crawler/ ./

# Build the TypeScript project into JavaScript
RUN npm run build


# Stage 2: Create the final Python application image
FROM python:3.11-slim

WORKDIR /app

ENV PYTHONPATH=/app

# Install Python dependencies
COPY apps-microservices/crawler-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the Python application code
COPY apps-microservices/crawler-service/app ./app
COPY main.py .

# Copy the compiled crawler from the builder stage
COPY --from=builder apps-microservices/crawler-service/app/crawler/dist ./crawler/dist
COPY --from=builder apps-microservices/crawler-service/app/crawler/node_modules ./crawler/node_modules

# Expose the port for the FastAPI application
EXPOSE 8503

# Command to run the FastAPI server
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8503"]