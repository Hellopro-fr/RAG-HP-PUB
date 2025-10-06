FROM python:3.10-slim as builder

# Installer les dépendances système (compilateur protobuf)
RUN apt-get update && apt-get install -y protobuf-compiler && rm -rf /var/lib/apt/lists/*

WORKDIR /app
ENV PYTHONPATH=/app

COPY apps-microservices/optimize-service/requirements.txt .

ENV PIP_TARGET=/app/wheelhouse

RUN pip install --no-cache-dir -r requirements.txt --target=${PIP_TARGET}

FROM python:3.10-slim

WORKDIR /app
ENV PYTHONPATH=/app

COPY --from=builder /app/wheelhouse /usr/local/lib/python3.10/site-packages

COPY protos /app/protos
COPY libs/ /app/libs/
RUN pip install --no-cache-dir -e ./libs/common-utils

RUN find /app/protos/grpc_stubs -name "*.proto" | xargs python -m grpc_tools.protoc -I/app/protos --python_out=/app/libs/grpc-stubs/src --grpc_python_out=/app/libs/grpc-stubs/src
RUN pip install --no-cache-dir -e ./libs/grpc-stubs

COPY apps-microservices/optimize-service/app ./app
COPY apps-microservices/optimize-service/main.py .

EXPOSE 8563

# --- Commande de Lancement ---
# Utilisation de Gunicorn pour gérer les workers
CMD ["python","-m","gunicorn", \
     "-w", "8", \
     "-k", "uvicorn.workers.UvicornWorker", \
     "--bind", "0.0.0.0:8563", \
     "--timeout", "120", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "main:app"]