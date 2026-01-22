FROM python:3.10-slim

WORKDIR /app
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

COPY apps-microservices/graph-rag-llm-extractor-processor/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY libs /app/libs
COPY protos /app/protos
RUN python -m grpc_tools.protoc -I/app/protos --python_out=/app/libs/grpc-stubs/src --grpc_python_out=/app/libs/grpc-stubs/src /app/protos/grpc_stubs/*.proto
RUN pip install -e /app/libs/grpc-stubs
RUN pip install -e /app/libs/common-utils

COPY apps-microservices/graph-rag-llm-extractor-processor/app ./app

EXPOSE 8561
CMD ["python", "-m", "app.main"]
