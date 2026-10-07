# Test image shared by libs/unit-registry, unit-registry-service and
# graph-rag-normalize-unite-service. Built once by scripts/unit-registry-test.sh;
# rebuild with REBUILD=1 when a dependency below changes.
FROM python:3.10-slim
RUN pip install --no-cache-dir \
    pint==0.24.4 \
    "SQLAlchemy==2.0.36" "PyMySQL==1.1.1" cryptography \
    "grpcio==1.68.1" "grpcio-tools==1.68.1" "protobuf>=5.26.1,<6" \
    "pydantic>=2" "pydantic-settings>=2" \
    "pika==1.3.2" prometheus-client waitress redis \
    "pytest==8.3.3"
