# prix-extraction-siteweb Dockerfile

FROM python:3.10-slim
RUN apt-get update && apt-get install -y protobuf-compiler && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Installer la librairie partagée
COPY libs/common-utils /app/libs/common-utils
RUN pip install -e /app/libs/common-utils

# Installer les requirements
COPY apps-microservices/prix-extraction-siteweb/requirements.txt .
RUN pip install -r requirements.txt

# Installer aussi les dépendances de l'API recherche (nécessaires pour api_recherche_lib / Milvus)
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

# Copier les modules de l'API recherche pour utilisation interne (recherche Milvus)
# Créer un package Python nommé "api_recherche_lib" pour éviter les conflits avec "app"
COPY apps-microservices/api-recherche/app /app/api_recherche_lib

# Corriger les imports internes: remplacer "from app." par "from api_recherche_lib."
# Cela permet aux modules de api_recherche_lib de s'importer entre eux correctement
RUN find /app/api_recherche_lib -type f -name "*.py" -exec sed -i 's/from app\./from api_recherche_lib./g' {} \;
RUN find /app/api_recherche_lib -type f -name "*.py" -exec sed -i 's/import app\./import api_recherche_lib./g' {} \;

# Le PYTHONPATH /app permet d'importer: from api_recherche_lib.core.recherche import ...

# Copier le code source
COPY apps-microservices/prix-extraction-siteweb/app ./app
COPY apps-microservices/prix-extraction-siteweb/main.py .

# Pas d'EXPOSE nécessaire - service RabbitMQ consumer

# Lancer en mode RabbitMQ consumer
CMD ["python", "main.py"]
