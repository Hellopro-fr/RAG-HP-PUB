FROM python:3.10-slim
RUN apt-get update && apt-get install -y protobuf-compiler && rm -rf /var/lib/apt/lists/*

WORKDIR /app
ENV PYTHONPATH=/app

COPY apps-microservices/api-recherche/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# --- Installation des Dépendances ---
COPY libs /app/libs
COPY protos /app/protos
RUN python -m grpc_tools.protoc -I/app/protos --python_out=/app/libs/grpc-stubs/src --grpc_python_out=/app/libs/grpc-stubs/src /app/protos/grpc_stubs/*.proto
RUN pip install -e /app/libs/grpc-stubs
RUN pip install -e /app/libs/common-utils

# --- Copie du Code Source ---
COPY apps-microservices/reranking-model-service/app ./app
COPY apps-microservices/reranking-model-service/application ./application
COPY apps-microservices/reranking-model-service/infrastructure ./infrastructure

EXPOSE 50053
CMD ["python", "-m", "app.main"]