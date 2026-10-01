FROM python:3.11-slim

# curl is used by the Docker healthcheck.
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY apps-microservices/mcp-template-neo4j-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY apps-microservices/mcp-template-neo4j-service/app /app/app
COPY apps-microservices/mcp-template-neo4j-service/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Non-root
RUN useradd -u 1000 -m runner
USER runner

EXPOSE 8598
# Dynamic instance ports (15100-15199) are exposed via docker-compose `expose:`.
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8598"]
