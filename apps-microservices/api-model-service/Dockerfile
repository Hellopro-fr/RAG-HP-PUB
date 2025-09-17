FROM python:3.10-slim

RUN apt-get update && apt-get install -y protobuf-compiler && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY libs /app/libs

COPY protos /app/protos
COPY apps-microservices/api-model-service/requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# CORRECTION: Remplacement de la commande unique par des commandes explicites.
# On utilise '&& \' pour enchaîner les commandes en une seule couche Docker (RUN) pour l'efficacité.
RUN find ./protos -name "*.proto" | xargs python -m grpc_tools.protoc -I./protos --python_out=. --grpc_python_out=.

RUN pip install -e /app/libs/grpc-stubs
RUN pip install -e /app/libs/common-utils

# Copie du code source de l'application
COPY apps-microservices/api-model-service/app /app/app

EXPOSE 8599

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8599"]