FROM python:3.11-slim
WORKDIR /app

COPY apps-microservices/mcp-neo4j-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY apps-microservices/mcp-neo4j-service/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

EXPOSE 8587

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["mcp-proxy", "--port", "8587", "--host", "0.0.0.0", "--pass-environment", "--allow-origin", "*", "--stateless", "--", "mcp-neo4j-cypher"]
