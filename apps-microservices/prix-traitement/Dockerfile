# apps-microservices/prix-traitement/Dockerfile

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
COPY apps-microservices/prix-traitement/requirements.txt .
RUN pip install -r requirements.txt

# Installer aussi les dépendances de l'API recherche (nécessaires pour api_recherche_lib / Milvus)
COPY apps-microservices/api-recherche/requirements.txt /tmp/api-recherche-requirements.txt
RUN pip install -r /tmp/api-recherche-requirements.txt && rm /tmp/api-recherche-requirements.txt

COPY libs/grpc-stubs /app/libs/grpc-stubs
RUN find /app/libs/grpc-stubs/src/grpc_stubs -name "*.py" -delete

COPY protos /app/protos
RUN find /app/protos/grpc_stubs -name "*.proto" | xargs python -m grpc_tools.protoc -I/app/protos --python_out=/app/libs/grpc-stubs/src --grpc_python_out=/app/libs/grpc-stubs/src
RUN pip install -e /app/libs/grpc-stubs

# Copier les modules de l'API recherche pour utilisation interne (recherche Milvus)
# Créer un package Python nommé "api_recherche_lib" pour éviter les conflits avec "app"
COPY apps-microservices/api-recherche/app /app/api_recherche_lib

# Corriger les imports internes: remplacer "from app." par "from api_recherche_lib."
# Cela permet aux modules de api_recherche_lib de s'importer entre eux correctement
RUN find /app/api_recherche_lib -type f -name "*.py" -exec sed -i 's/from app\./from api_recherche_lib./g' {} \;
RUN find /app/api_recherche_lib -type f -name "*.py" -exec sed -i 's/import app\./import api_recherche_lib./g' {} \;

# Le PYTHONPATH /app permet d'importer: from api_recherche_lib.core.recherche import ...

# Étape 3: Copier le code source de manière propre
COPY apps-microservices/prix-traitement/app ./app
COPY apps-microservices/prix-traitement/main.py .

# Étape 4: Exposer le port
EXPOSE 8591

# Étape 5: Définir la commande de lancement directement
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8591"]
