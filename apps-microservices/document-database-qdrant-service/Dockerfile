FROM python:3.11-slim
WORKDIR /app

# Dit à Python de toujours chercher les modules à partir du dossier /app.
ENV PYTHONPATH=/app

COPY apps-microservices/document-database-qdrant-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copier la lib partagée
COPY libs/ /app/libs/
RUN pip install --no-cache-dir -e ./libs/common-utils

COPY apps-microservices/document-database-qdrant-service/app/ /app/document_database_qdrant_service

RUN useradd -m -r appuser
USER appuser

CMD ["python", "-u", "-m", "document_database_qdrant_service.main"]