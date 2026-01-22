FROM python:3.10-slim
RUN apt-get update && apt-get install -y protobuf-compiler build-essential && rm -rf /var/lib/apt/lists/*

WORKDIR /app
ENV PYTHONPATH=/app

COPY apps-microservices/graph-rag-spacy-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN python -m spacy download fr_core_news_sm

# --- Install Dependencies ---
COPY libs /app/libs
COPY protos /app/protos
RUN python -m grpc_tools.protoc -I/app/protos --python_out=/app/libs/grpc-stubs/src --grpc_python_out=/app/libs/grpc-stubs/src /app/protos/grpc_stubs/*.proto
RUN pip install -e /app/libs/grpc-stubs
RUN pip install -e /app/libs/common-utils

# --- Copy Source Code ---
COPY apps-microservices/graph-rag-spacy-service/app ./app
COPY apps-microservices/graph-rag-spacy-service/application ./application
COPY apps-microservices/graph-rag-spacy-service/infrastructure ./infrastructure

EXPOSE 50058
EXPOSE 8569
CMD ["python", "-m", "app.main"]
