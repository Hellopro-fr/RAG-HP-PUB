FROM python:3.10-slim

ENV PYTHONPATH="/app/libs/common-utils/src:${PYTHONPATH}"
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Copy and install requirements
COPY apps-microservices/prix-milvus-processor/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared library
COPY libs/common-utils /app/libs/common-utils
RUN pip install -e /app/libs/common-utils

# Copy service code
COPY apps-microservices/prix-milvus-processor/app /app/app

# Expose Prometheus metrics port
EXPOSE 8010

CMD ["python", "-m", "app.main"]
