# Stage 1: Build Go CLIs
FROM golang:1.24-alpine AS go-builder
WORKDIR /src
RUN apk add --no-cache git
RUN go install github.com/markusmobius/go-trafilatura/cmd/go-trafilatura@latest
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
COPY --from=go-builder /go/bin/go-trafilatura /usr/local/bin/go-trafilatura
COPY --from=go-builder /go/bin/go-readability /usr/local/bin/go-readability

# Copy the Node.js runtime and its globally installed modules from the builder stage.
COPY --from=node-builder /usr/local/bin/node /usr/local/bin/node
COPY --from=node-builder /usr/local/lib/node_modules /usr/local/lib/node_modules

# Create a symlink to the readability-cli executable, named 'readability-js' for our app.
# This mimics how 'npm install -g' works and is crucial for the script to find its dependencies.
RUN ln -s /usr/local/lib/node_modules/readability-cli/cli.js /usr/local/bin/readability-js

# Set NODE_PATH so globally installed Node modules can be found by their executables.
ENV NODE_PATH /usr/local/lib/node_modules

# Install Python dependencies
COPY apps-microservices/extractor-testing-service/backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY apps-microservices/extractor-testing-service/backend /app

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8034"]