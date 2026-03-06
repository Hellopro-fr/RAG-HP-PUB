# prix-extraction-message Dockerfile

FROM python:3.10-slim
RUN apt-get update && apt-get install -y protobuf-compiler && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Installer la librairie partagée
COPY libs/common-utils /app/libs/common-utils
RUN pip install -e /app/libs/common-utils

# Installer les requirements
COPY apps-microservices/prix-extraction-message/requirements.txt .
RUN pip install -r requirements.txt

# Copier et installer les stubs gRPC
COPY libs/grpc-stubs /app/libs/grpc-stubs
RUN find /app/libs/grpc-stubs/src/grpc_stubs -name "*.py" -delete

# Copier les protos
COPY protos /app/protos

# Générer les stubs gRPC à partir des protos
RUN find /app/protos/grpc_stubs -name "*.proto" | xargs python -m grpc_tools.protoc -I/app/protos --python_out=/app/libs/grpc-stubs/src --grpc_python_out=/app/libs/grpc-stubs/src
RUN pip install -e /app/libs/grpc-stubs

# Copier le code source
COPY apps-microservices/prix-extraction-message/app ./app
COPY apps-microservices/prix-extraction-message/main.py .

# Lancer en mode RabbitMQ consumer
CMD ["python", "main.py"]
