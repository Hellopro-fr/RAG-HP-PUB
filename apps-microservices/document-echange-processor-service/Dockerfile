# --- Étape 0: Base ---
FROM python:3.11-slim
WORKDIR /app

# --- Étape 1: Définir le PYTHONPATH ---
ENV PYTHONPATH=/app

RUN apt-get update && apt-get install -y curl git \
    && rm -rf /var/lib/apt/lists/*

# --- Étape 2: Installer uv ---
RUN curl -LsSf https://astral.sh/uv/install.sh | sh

# --- Étape 3: Installer les dépendances du projet ---

# Copier la lib partagée
COPY libs/common-utils /app/libs/common-utils
RUN pip install -e /app/libs/common-utils

# Copier les requirements du service
COPY apps-microservices/document-echange-processor-service/requirements.txt .
RUN pip install -r requirements.txt

# Copier le code source principal
COPY apps-microservices/document-echange-processor-service/app/ \
     /app/document_echange_processor_service

# # Installer docext depuis PyPI (optionnel)
# RUN uv pip install docext

# Installer docext depuis la source
RUN git clone https://github.com/nanonets/docext.git
WORKDIR /app/docext
RUN apt-get update && apt-get install -y poppler-utils && rm -rf /var/lib/apt/lists/*
RUN uv pip install -e .

WORKDIR /app
# --- Étape 4: Copier le script entrypoint ---
COPY apps-microservices/document-echange-processor-service/entrypoint.sh .
RUN chmod +x entrypoint.sh

# --- Étape 5: Exposer le port du serveur docext ---
EXPOSE 8559

# --- Étape 6: Définir le point d'entrée ---
CMD ["/app/entrypoint.sh"]
