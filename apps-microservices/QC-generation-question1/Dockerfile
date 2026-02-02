# QC-generation-question1 Dockerfile

FROM python:3.10-slim
RUN apt-get update && apt-get install -y protobuf-compiler && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Installer la librairie partagée
COPY libs/common-utils /app/libs/common-utils
RUN pip install -e /app/libs/common-utils

# Installer les requirements
COPY apps-microservices/QC-generation-question1/requirements.txt .
RUN pip install -r requirements.txt

COPY libs/grpc-stubs /app/libs/grpc-stubs
RUN find /app/libs/grpc-stubs/src/grpc_stubs -name "*.py" -delete

COPY protos /app/protos
RUN find /app/protos/grpc_stubs -name "*.proto" | xargs python -m grpc_tools.protoc -I/app/protos --python_out=/app/libs/grpc-stubs/src --grpc_python_out=/app/libs/grpc-stubs/src
RUN pip install -e /app/libs/grpc-stubs

# Copier le code source
COPY apps-microservices/QC-generation-question1/app ./app
COPY apps-microservices/QC-generation-question1/main.py .

# Pas d'EXPOSE nécessaire - service RabbitMQ consumer

# Lancer en mode RabbitMQ consumer
CMD ["python", "main.py"]