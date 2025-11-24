# Stage 1: Build Go CLIs
FROM golang:1.24-alpine AS go-builder
WORKDIR /src

# Install system dependencies
RUN apk add --no-cache git

# Build custom go-trafilatura script
COPY apps-microservices/extractor-testing-service/backend/go-extractor /src/go-extractor
WORKDIR /src/go-extractor
RUN go mod tidy
RUN go build -o go-trafilatura-hp main.go

# Build go-readability CLI
RUN go install github.com/go-shiori/go-readability/cmd/go-readability@latest

# Stage 2: Build Node.js CLI
FROM node:20-slim AS node-builder
WORKDIR /app
RUN npm install -g readability-cli
# The executable created is named 'readable'. Verify it exists.
RUN test -f /usr/local/bin/readable || (echo "'readable' CLI not found after installation!" && exit 1)

# Stage 3: Final Python Application
FROM python:3.11-slim
WORKDIR /app

# Install build-essential for C++ compilation and default-jre-headless for Java runtime (for boilerpipe3).
RUN apt-get update && apt-get install -y --no-install-recommends build-essential default-jre-headless && rm -rf /var/lib/apt/lists/*

# Copy binaries from builder stages
COPY --from=go-builder /src/go-extractor/go-trafilatura-hp /usr/local/bin/go-trafilatura-hp
COPY --from=go-builder /go/bin/go-readability /usr/local/bin/go-readability

# Copy the entire Node.js environment from the builder stage. This includes the
# binary, global modules, and bin scripts/symlinks, ensuring perfect parity.
COPY --from=node-builder /usr/local/ /usr/local/

# Install shared library
COPY libs/common-utils /app/libs/common-utils
RUN pip install -e /app/libs/common-utils

# Install Python dependencies
COPY apps-microservices/extractor-testing-service/backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY apps-microservices/extractor-testing-service/backend /app

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8034"]