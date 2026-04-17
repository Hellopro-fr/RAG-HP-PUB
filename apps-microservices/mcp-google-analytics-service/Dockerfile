FROM python:3.10-slim
WORKDIR /app

COPY apps-microservices/mcp-google-analytics-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY apps-microservices/mcp-google-analytics-service/entrypoint.sh /app/entrypoint.sh
COPY apps-microservices/mcp-google-analytics-service/p12_to_json.py /app/p12_to_json.py
RUN chmod +x /app/entrypoint.sh

ENV MCP_PORT=8583
EXPOSE ${MCP_PORT}

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["sh", "-c", "mcp-proxy --port ${MCP_PORT} --host 0.0.0.0 --pass-environment --allow-origin '*' --stateless -- analytics-mcp"]
