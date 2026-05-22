# apps-microservices/api-rest-milvus/Dockerfile

FROM python:3.10-slim
WORKDIR /app

# Étape 1: Définir le PYTHONPATH pour que les imports fonctionnent
ENV PYTHONPATH=/app
# SERVICE_NAME drives the Redis CLIENT SETNAME prefix from common_utils
# (cache_service). Overridable at runtime via docker-compose env.
ENV SERVICE_NAME=api-rest-milvus


# Ensuite, on copie et installe les requirements spécifiques à ce service
COPY apps-microservices/api-rest-milvus/requirements.txt .
RUN pip install -r requirements.txt


# Étape 3: Copier le code source de manière propre
# On copie le code de l'application dans son propre dossier NOMMÉ et UNIQUE
COPY apps-microservices/api-rest-milvus .

# Étape 2: Installer TOUTES les dépendances dans l'environnement global du conteneur
# D'abord, on copie et installe notre librairie partagée
COPY libs/common-utils /app/libs/common-utils
RUN pip install -e /app/libs/common-utils

# Étape 4: Exposer le port
EXPOSE 8517

# Étape 5: Définir la commande de lancement directement
# On lance Uvicorn en lui disant de trouver le module 'main' dans le paquet 'api_rest-milvus_service'
# Le port est défini dynamiquement par la variable $PORT de Render, avec une valeur par défaut de 8517.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8517"]