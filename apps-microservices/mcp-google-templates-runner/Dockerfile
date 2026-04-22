FROM python:3.11-slim

# coreutils provides shred (used by the credentials manager to wipe tmpfs files).
# curl is used by the Docker healthcheck.
RUN apt-get update && apt-get install -y --no-install-recommends coreutils curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY apps-microservices/mcp-google-templates-runner/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY apps-microservices/mcp-google-templates-runner/app /app/app
COPY apps-microservices/mcp-google-templates-runner/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Non-root
RUN useradd -u 1000 -m runner
USER runner

EXPOSE 8594
# Dynamic instance ports (from config) are exposed via docker-compose `expose:` declarations.
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8594"]
