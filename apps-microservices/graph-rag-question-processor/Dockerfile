FROM python:3.10-slim

WORKDIR /app
ENV PYTHONPATH=/app

COPY apps-microservices/graph-rag-question-processor/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# --- Install Dependencies ---
COPY libs /app/libs
COPY protos /app/protos
RUN python -m grpc_tools.protoc -I/app/protos --python_out=/app/libs/grpc-stubs/src --grpc_python_out=/app/libs/grpc-stubs/src /app/protos/grpc_stubs/*.proto
RUN pip install -e /app/libs/grpc-stubs
RUN pip install -e /app/libs/common-utils

# --- Copy Source Code ---
COPY apps-microservices/graph-rag-question-processor/app ./app

CMD ["python", "-m", "app.main"]
