# --- Étape 0: Base ---
FROM python:3.11-slim
WORKDIR /app

# --- Étape 1: Définir le PYTHONPATH ---
ENV PYTHONPATH=/app

RUN apt-get update && apt-get install -y git protobuf-compiler \
    && rm -rf /var/lib/apt/lists/*

# Copier les requirements du service
COPY apps-microservices/document-echange-processor-service/requirements.txt .
RUN pip install -r requirements.txt

COPY libs/grpc-stubs /app/libs/grpc-stubs
RUN find /app/libs/grpc-stubs/src/grpc_stubs -name "*.py" -delete

# Copier la lib partagée
COPY protos /app/protos
COPY libs/ /app/libs/
RUN pip install --no-cache-dir -e ./libs/common-utils

RUN find /app/protos/grpc_stubs -name "*.proto" | xargs python -m grpc_tools.protoc -I/app/protos --python_out=/app/libs/grpc-stubs/src --grpc_python_out=/app/libs/grpc-stubs/src
RUN pip install --no-cache-dir -e ./libs/grpc-stubs

# Copier le code source principal
COPY apps-microservices/document-echange-processor-service/app/ \
     /app/document_echange_processor_service

# # Installer docext depuis PyPI (optionnel)
# RUN uv pip install docext

# Installer docext depuis la source
RUN git clone https://github.com/nanonets/docext.git
WORKDIR /app/docext
RUN apt-get update && apt-get install -y poppler-utils && rm -rf /var/lib/apt/lists/*
RUN pip install -e .

WORKDIR /app
# --- Étape 4: Copier le script entrypoint ---
COPY apps-microservices/document-echange-processor-service/entrypoint.sh .
RUN chmod +x entrypoint.sh

# --- Étape 5: Exposer le port du serveur docext ---
EXPOSE 8559

# --- Étape 6: Définir le point d'entrée ---
CMD ["/app/entrypoint.sh"]
