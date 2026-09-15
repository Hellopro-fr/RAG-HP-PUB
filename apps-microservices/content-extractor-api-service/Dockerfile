FROM python:3.10-slim
# refresh OS packages of the final stage (fixable CVEs in base layers)
RUN apt-get update && apt-get -y upgrade && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV PYTHONPATH=/app

# Install common-utils first (shared library)
COPY libs/common-utils /app/libs/common-utils
RUN pip install --no-cache-dir -e /app/libs/common-utils

# Install service dependencies
COPY apps-microservices/content-extractor-api-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy service source
COPY apps-microservices/content-extractor-api-service/main.py .
COPY apps-microservices/content-extractor-api-service/app ./app

# Non-root user
RUN useradd --create-home appuser
USER appuser

EXPOSE 8600

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl --fail http://localhost:8600/health || exit 1

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port 8600 --proxy-headers --workers ${UVICORN_WORKERS:-2}"]
