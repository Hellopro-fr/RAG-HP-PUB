FROM python:3.10-slim

WORKDIR /app
ENV PYTHONPATH=/app PYTHONUNBUFFERED=1

COPY apps-microservices/unit-registry-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY libs /app/libs
COPY protos /app/protos
RUN python -m grpc_tools.protoc -I/app/protos --python_out=/app/libs/grpc-stubs/src \
      --grpc_python_out=/app/libs/grpc-stubs/src /app/protos/grpc_stubs/*.proto \
 && pip install --no-cache-dir -e /app/libs/grpc-stubs -e /app/libs/unit-registry

COPY apps-microservices/unit-registry-service/app ./app
COPY apps-microservices/unit-registry-service/application ./application
COPY apps-microservices/unit-registry-service/infrastructure ./infrastructure

RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin registry
USER registry

EXPOSE 50059 8571
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8571/health', timeout=3).status == 200 else 1)"
CMD ["python", "-m", "app.main"]
