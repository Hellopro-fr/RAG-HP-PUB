# Stage 1: Build the React frontend
FROM node:20.19.0-alpine3.21 AS build-frontend
WORKDIR /app/frontend

# Install pnpm
RUN npm install -g pnpm

# Copy package manifests to leverage Docker cache
COPY apps-microservices/dlq-manager-service/frontend/package.json ./
COPY apps-microservices/dlq-manager-service/frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

# Copy the rest of the frontend source code
COPY apps-microservices/dlq-manager-service/frontend/ ./

# Build the static files
RUN pnpm run build

# Stage 2: Build the FastAPI backend
FROM python:3.10.17-slim AS build-backend
WORKDIR /app/backend

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Copy requirements and install dependencies
COPY apps-microservices/dlq-manager-service/backend/requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy the backend source code
COPY apps-microservices/dlq-manager-service/backend/ ./

# Stage 3: Final production image
FROM python:3.10.17-slim
WORKDIR /app

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Copy dependencies from the backend build stage
COPY --from=build-backend /usr/local/lib/python3.10/site-packages /usr/local/lib/python3.10/site-packages
COPY --from=build-backend /usr/local/bin /usr/local/bin

# Copy the backend application code
COPY --from=build-backend /app/backend /app

# Copy the built frontend static files from the Next.js export
COPY --from=build-frontend /app/frontend/out /app/static

# Run as non-root user
RUN useradd -r -u 1001 appuser && chown -R appuser /app
USER appuser

# Expose the port the app runs on
EXPOSE 8560

# Healthcheck against the API
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8560/api/rules')" || exit 1

# Run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8560"]
