# apps-microservices/api-classification/Dockerfile

FROM python:3.10-slim

WORKDIR /app

# Étape 2: Installer TOUTES les dépendances dans l'environnement global du conteneur
# D'abord, on copie et installe notre librairie partagée
COPY libs/common-utils /app/libs/common-utils
RUN pip install -e /app/libs/common-utils

# Étape 1: Définir le PYTHONPATH pour que les imports fonctionnent (APRÈS installation)
ENV PYTHONPATH=/app:/app/libs/common-utils/src 

# Ensuite, on copie et installe les requirements spécifiques à ce service
COPY apps-microservices/api-classification/requirements.txt .
RUN pip install -r requirements.txt

# Copier et installer les stubs gRPC
COPY libs/grpc-stubs /app/libs/grpc-stubs
RUN find /app/libs/grpc-stubs/src/grpc_stubs -name "*.py" -delete

# Copier les protos
COPY protos /app/protos

# Générer les stubs gRPC à partir des protos
RUN find /app/protos/grpc_stubs -name "*.proto" | xargs python -m grpc_tools.protoc -I/app/protos --python_out=/app/libs/grpc-stubs/src --grpc_python_out=/app/libs/grpc-stubs/src

RUN pip install -e /app/libs/grpc-stubs

# Étape 3: Copier le code source de manière propre
# On copie le code de l'application dans son propre dossier NOMMÉ et UNIQUE
COPY apps-microservices/api-classification/app ./app
COPY apps-microservices/api-classification/main.py .

# Étape 4: Exposer le port
EXPOSE 8577

# Étape 5: Définir la commande de lancement directement
# On lance Uvicorn en lui disant de trouver le module 'main' dans le paquet 'api_ingestion_service'
# Le port est défini dynamiquement par la variable $PORT de Render, avec une valeur par défaut de 8510.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8577"]