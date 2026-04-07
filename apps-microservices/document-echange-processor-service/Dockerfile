# --- Étape 0: Base ---
FROM python:3.11-slim
WORKDIR /app

# --- Étape 1: Définir le PYTHONPATH ---
ENV PYTHONPATH=/app

RUN apt-get update && apt-get install -y --no-install-recommends libreoffice \
    && rm -rf /var/lib/apt/lists/*

# Copier les requirements du service
COPY apps-microservices/document-echange-processor-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copier la lib partagée
COPY libs/ /app/libs/
RUN pip install --no-cache-dir -e ./libs/common-utils

# Install spaCy model required by Presidio (AnonymizeText)
RUN python -m spacy download en_core_web_lg

# Copier le code source principal
COPY apps-microservices/document-echange-processor-service/app/ \
     /app/document_echange_processor_service

RUN useradd -m -r appuser
USER appuser

CMD ["python", "-u" ,"-m" ,"document_echange_processor_service.main"]
