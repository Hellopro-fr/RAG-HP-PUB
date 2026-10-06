FROM python:3.10-slim
RUN apt-get update && apt-get install -y --no-install-recommends protobuf-compiler && rm -rf /var/lib/apt/lists/*

WORKDIR /app
ENV PYTHONPATH=/app

COPY apps-microservices/graph-rag-normalize-unite-service-dynamique/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# --- Install Dependencies ---
COPY libs /app/libs
COPY protos /app/protos
RUN python -m grpc_tools.protoc -I/app/protos --python_out=/app/libs/grpc-stubs/src --grpc_python_out=/app/libs/grpc-stubs/src /app/protos/grpc_stubs/*.proto
RUN pip install -e /app/libs/grpc-stubs
RUN pip install -e /app/libs/common-utils

# --- Copy Source Code ---
COPY apps-microservices/graph-rag-normalize-unite-service-dynamique/app ./app
COPY apps-microservices/graph-rag-normalize-unite-service-dynamique/application ./application
COPY apps-microservices/graph-rag-normalize-unite-service-dynamique/infrastructure ./infrastructure

# gRPC 50057 (contrat historique) + REST 8567 + Prometheus 8557
EXPOSE 50057 8567 8557
CMD ["python", "-m", "app.main"]
