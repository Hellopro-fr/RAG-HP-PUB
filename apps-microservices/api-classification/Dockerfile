# apps-microservices/api-classification/Dockerfile

FROM python:3.10-slim
RUN apt-get update && apt-get install -y protobuf-compiler && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Étape 1: Définir le PYTHONPATH pour que les imports fonctionnent
ENV PYTHONPATH=/app

# Étape 2: Installer TOUTES les dépendances dans l'environnement global du conteneur
# D'abord, on copie et installe notre librairie partagée
COPY libs/common-utils /app/libs/common-utils
RUN pip install -e /app/libs/common-utils 

# Ensuite, on copie et installe les requirements spécifiques à ce service
COPY apps-microservices/api-classification/requirements.txt .
RUN pip install -r requirements.txt

# Installer aussi les dépendances de l'API recherche (nécessaires pour api_recherche_lib)
COPY apps-microservices/api-recherche/requirements.txt /tmp/api-recherche-requirements.txt
RUN pip install -r /tmp/api-recherche-requirements.txt && rm /tmp/api-recherche-requirements.txt

# Copier et installer les stubs gRPC
COPY libs/grpc-stubs /app/libs/grpc-stubs
RUN find /app/libs/grpc-stubs/src/grpc_stubs -name "*.py" -delete

# Copier les protos
COPY protos /app/protos

# Générer les stubs gRPC à partir des protos
RUN find /app/protos/grpc_stubs -name "*.proto" | xargs python -m grpc_tools.protoc -I/app/protos --python_out=/app/libs/grpc-stubs/src --grpc_python_out=/app/libs/grpc-stubs/src

RUN pip install -e /app/libs/grpc-stubs

# Étape 3: Copier les modules de l'API recherche pour utilisation interne
# Créer un package Python nommé "api_recherche_lib" pour éviter les conflits avec "app"
COPY apps-microservices/api-recherche/app /app/api_recherche_lib
# Le PYTHONPATH /app permet d'importer: from api_recherche_lib.core.recherche import ...

# Étape 4: Copier le code source de manière propre
# On copie le code de l'application dans son propre dossier NOMMÉ et UNIQUE
COPY apps-microservices/api-classification/app ./app
COPY apps-microservices/api-classification/main.py .

# Étape 5: Exposer le port
EXPOSE 8577

# Étape 6: Définir la commande de lancement directement
# On lance Uvicorn pour le service api-classification sur le port 8577
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8577"]