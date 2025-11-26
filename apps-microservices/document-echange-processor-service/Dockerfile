# --- Étape 0: Base ---
FROM python:3.11-slim
WORKDIR /app

# --- Étape 1: Définir le PYTHONPATH ---
ENV PYTHONPATH=/app

RUN apt-get update && apt-get install -y libreoffice \
    && rm -rf /var/lib/apt/lists/*

# Copier les requirements du service
COPY apps-microservices/document-echange-processor-service/requirements.txt .
RUN pip install -r requirements.txt

# Copier la lib partagée
COPY libs/ /app/libs/
RUN pip install --no-cache-dir -e ./libs/common-utils

# Copier le code source principal
COPY apps-microservices/document-echange-processor-service/app/ \
     /app/document_echange_processor_service

# --- Étape 6: Définir le point d'entrée ---
CMD ["python", "-u" ,"-m" ,"document_echange_processor_service.main"]
