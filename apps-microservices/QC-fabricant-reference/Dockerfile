# QC-fabricant-reference — extraction marque / reference (etape PSI 16)
# Ni gRPC ni protobuf : ce service n'appelle qu'une API REST et un LLM.

FROM python:3.10-slim

WORKDIR /app

ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1

# Bibliotheque partagee (DLQPropertiesAsync) — n'exige que redis
COPY libs/common-utils /app/libs/common-utils
RUN pip install --no-cache-dir -e /app/libs/common-utils

COPY apps-microservices/QC-fabricant-reference/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY apps-microservices/QC-fabricant-reference/app ./app
COPY apps-microservices/QC-fabricant-reference/main.py .

RUN useradd --create-home --shell /usr/sbin/nologin appuser \
    && mkdir -p /app/tracking /app/fichiers \
    && chown -R appuser:appuser /app
USER appuser

CMD ["python", "main.py"]
