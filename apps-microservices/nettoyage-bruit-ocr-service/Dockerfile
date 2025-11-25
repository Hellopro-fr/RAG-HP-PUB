FROM python:3.11-slim
WORKDIR /app

# Dit à Python de toujours chercher les modules à partir du dossier /app.
ENV PYTHONPATH=/app

RUN apt-get update && apt-get install -y protobuf-compiler \
    && rm -rf /var/lib/apt/lists/*


COPY apps-microservices/nettoyage-bruit-ocr-service/requirements.txt .
RUN pip install -r requirements.txt

COPY libs/grpc-stubs /app/libs/grpc-stubs
RUN find /app/libs/grpc-stubs/src/grpc_stubs -name "*.py" -delete

# Copier la lib partagée
COPY protos /app/protos
COPY libs/ /app/libs/
RUN pip install --no-cache-dir -e ./libs/common-utils

RUN find /app/protos/grpc_stubs -name "*.proto" | xargs python -m grpc_tools.protoc -I/app/protos --python_out=/app/libs/grpc-stubs/src --grpc_python_out=/app/libs/grpc-stubs/src
RUN pip install --no-cache-dir -e ./libs/grpc-stubs


COPY apps-microservices/nettoyage-bruit-ocr-service/app/ /app/nettoyage_bruit_ocr_service

CMD ["python", "-u", "-m", "nettoyage_bruit_ocr_service.main"]