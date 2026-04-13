FROM python:3.11-slim
WORKDIR /app

COPY apps-microservices/mcp-google-search-console-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Patch mcp-gsc: fix str/int comparison in get_sitemaps + None coverageState in check_indexing_issues
COPY apps-microservices/mcp-google-search-console-service/mcp_gsc/__init__.py /usr/local/lib/python3.11/site-packages/mcp_gsc/__init__.py

COPY apps-microservices/mcp-google-search-console-service/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

EXPOSE 8584

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["mcp-proxy", "--port", "8584", "--host", "0.0.0.0", "--pass-environment", "--allow-origin", "*", "--stateless", "--", "mcp-gsc"]
