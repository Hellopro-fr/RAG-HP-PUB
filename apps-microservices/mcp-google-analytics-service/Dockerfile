FROM python:3.10-slim
WORKDIR /app

COPY apps-microservices/mcp-google-analytics-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY apps-microservices/mcp-google-analytics-service/entrypoint.sh /app/entrypoint.sh
COPY apps-microservices/mcp-google-analytics-service/p12_to_json.py /app/p12_to_json.py
RUN chmod +x /app/entrypoint.sh

EXPOSE 8583

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["mcp-proxy", "--port", "8583", "--host", "0.0.0.0", "--pass-environment", "--allow-origin", "*", "--stateless", "--", "analytics-mcp"]
