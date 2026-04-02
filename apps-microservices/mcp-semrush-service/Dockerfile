FROM node:20-slim

RUN apt-get update && apt-get install -y python3 python3-pip python3-venv && rm -rf /var/lib/apt/lists/*
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir mcp-proxy>=0.11.0

WORKDIR /app
COPY apps-microservices/mcp-semrush-service/package.json .
RUN npm install

COPY apps-microservices/mcp-semrush-service/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

EXPOSE 8588

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["mcp-proxy", "--port", "8588", "--host", "0.0.0.0", "--pass-environment", "--allow-origin", "*", "--stateless", "--", "npx", "semrush-mcp"]
