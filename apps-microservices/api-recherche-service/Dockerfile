FROM python:3.10-slim as builder

# Installer les dépendances système (compilateur protobuf)
RUN apt-get update && apt-get install -y protobuf-compiler && rm -rf /var/lib/apt/lists/*

WORKDIR /app
ENV PYTHONPATH=/app

COPY libs/common-utils /app/libs/common-utils
COPY apps-microservices/api-recherche-service/requirements.txt .
COPY libs/grpc-stubs/setup.py /app/libs/grpc-stubs/setup.py
COPY protos /app/protos

RUN pip install --no-cache-dir -r requirements.txt

ENV PIP_TARGET=/app/wheelhouse
RUN pip install --no-cache-dir -r requirements.txt --target=${PIP_TARGET}
RUN pip install --no-cache-dir -e /app/libs/common-utils --target=${PIP_TARGET}

RUN find /app/protos/grpc_stubs -name "*.proto" | xargs python -m grpc_tools.protoc -I/app/protos --python_out=/app/libs/grpc-stubs/src --grpc_python_out=/app/libs/grpc-stubs/src
RUN pip install --no-cache-dir -e /app/libs/grpc-stubs --target=${PIP_TARGET}

FROM python:3.10-slim

WORKDIR /app
ENV PYTHONPATH=/app

COPY --from=builder /app/wheelhouse /usr/local/lib/python3.10/site-packages

COPY apps-microservices/api-recherche/app ./app
COPY apps-microservices/api-recherche/main.py .

EXPOSE 8511

# --- Commande de Lancement ---
# Utilisation de Gunicorn pour gérer les workers
CMD ["gunicorn", \
     "-w", "4", \
     "-k", "uvicorn.workers.UvicornWorker", \
     "--bind", "0.0.0.0:8511", \
     "--timeout", "120", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "main:app"]