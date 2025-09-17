FROM python:3.10-slim
WORKDIR /app

# Étape 1: Définir le PYTHONPATH.
# Dit à Python de toujours chercher les modules à partir du dossier /app.
ENV PYTHONPATH=/app

# Étape 2: Installer les dépendances
# On copie la lib partagée
COPY libs/common-utils /app/libs/common-utils
RUN pip install -e /app/libs/common-utils
# On copie les requirements du service
# Étape 1: Définir le PYTHONPATH.
# Dit à Python de toujours chercher les modules à partir du dossier /app.
ENV PYTHONPATH=/app

# Étape 2: Installer les dépendances
# On copie la lib partagée
COPY libs/common-utils /app/libs/common-utils
RUN pip install -e /app/libs/common-utils
# On copie les requirements du service
COPY apps-microservices/embedding-service/requirements.txt .
RUN pip install -r requirements.txt

COPY libs/grpc-stubs /app/libs/grpc-stubs
RUN find /app/libs/grpc-stubs/src/grpc_stubs -name "*.py" -delete

COPY protos /app/protos
RUN find /app/protos/grpc_stubs -name "*.proto" | xargs python -m grpc_tools.protoc -I/app/protos --python_out=/app/libs/grpc-stubs/src --grpc_python_out=/app/libs/grpc-stubs/src
# RUN touch ./protos/__init__.py
RUN pip install -e /app/libs/grpc-stubs

# Étape 3: Copier le code source
# On copie le CONTENU du dossier app local directement dans le WORKDIR (/app)
COPY apps-microservices/embedding-service/app/ /app/embedding_service

# Étape 4: Définir la commande
# On peut maintenant exécuter le script directement, les imports fonctionneront grâce au PYTHONPATH.
CMD ["python", "-u", "-m", "embedding_service.main"]