# Utiliser une base Python cohérente avec les autres services
FROM python:3.11-slim
RUN apt-get update && apt-get install -y protobuf-compiler && rm -rf /var/lib/apt/lists/*

# Définir le répertoire de travail
WORKDIR /app

# Définir le PYTHONPATH est crucial pour que les imports fonctionnent
ENV PYTHONPATH=/app

# On copie la lib partagée
COPY libs/common-utils /app/libs/common-utils
RUN pip install -e /app/libs/common-utils
COPY libs/grpc-stubs /app/libs/grpc-stubs
RUN find /app/libs/grpc-stubs/src/grpc_stubs -name "*.py" -delete
COPY protos /app/protos

# Copier uniquement le fichier des dépendances en utilisant le chemin complet depuis la racine
COPY apps-microservices/template-llm-service/requirements.txt .

# Installer les dépendances
RUN pip install --no-cache-dir -r requirements.txt
RUN find /app/protos/grpc_stubs -name "*.proto" | xargs python -m grpc_tools.protoc -I/app/protos --python_out=/app/libs/grpc-stubs/src --grpc_python_out=/app/libs/grpc-stubs/src
RUN pip install -e /app/libs/grpc-stubs

# Copier le code source de l'application en utilisant le chemin complet depuis la racine
COPY apps-microservices/template-llm-service/app /app/template_llm_service

# La commande finale pour lancer le conteneur est maintenant notre script adaptatif.
CMD ["python", "-u", "-m", "template_llm_service.main"]