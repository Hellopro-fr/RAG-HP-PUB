# Stage 1: Build the React frontend
FROM node:18-alpine AS build-frontend
WORKDIR /app/frontend

# Copy package.json and potentially package-lock.json to leverage Docker cache
COPY apps-microservices/dlq-manager-service/frontend/package*.json ./
RUN npm install --legacy-peer-deps

# Copy the rest of the frontend source code
COPY apps-microservices/dlq-manager-service/frontend/ ./

# Build the static files
RUN npm run build

# Stage 2: Build the FastAPI backend
FROM python:3.10-slim AS build-backend
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
FROM python:3.10-slim
WORKDIR /app

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Copy dependencies from the backend build stage
COPY --from=build-backend /usr/local/lib/python3.10/site-packages /usr/local/lib/python3.10/site-packages
COPY --from=build-backend /usr/local/bin /usr/local/bin

# Copy the backend application code
COPY --from=build-backend /app/backend /app

# Copy the built frontend static files
COPY --from=build-frontend /app/frontend/build /app/static

# Expose the port the app runs on
EXPOSE 80

# Run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "80"]