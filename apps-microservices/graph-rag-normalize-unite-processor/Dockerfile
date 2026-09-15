FROM python:3.10-slim
# refresh OS packages of the final stage (fixable CVEs in base layers)
RUN apt-get update && apt-get -y upgrade && rm -rf /var/lib/apt/lists/*
RUN apt-get update && apt-get install -y protobuf-compiler && rm -rf /var/lib/apt/lists/*

WORKDIR /app
ENV PYTHONPATH=/app

COPY apps-microservices/graph-rag-normalize-unite-processor/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# --- Install Dependencies ---
COPY libs /app/libs
COPY protos /app/protos
RUN python -m grpc_tools.protoc -I/app/protos --python_out=/app/libs/grpc-stubs/src --grpc_python_out=/app/libs/grpc-stubs/src /app/protos/grpc_stubs/*.proto
RUN pip install -e /app/libs/grpc-stubs
RUN pip install -e /app/libs/common-utils

# --- Copy Source Code ---
COPY apps-microservices/graph-rag-normalize-unite-processor/app ./app

EXPOSE 8562
CMD ["python", "-m", "app.main"]
