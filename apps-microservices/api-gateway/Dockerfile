# apps-microservices/api-gateway/Dockerfile

FROM python:3.10-slim
WORKDIR /app

ENV PYTHONPATH=/app

COPY apps-microservices/api-gateway/requirements.txt .
RUN pip install -r requirements.txt

# Install shared libs (common_utils for Redis cache_service, etc.)
COPY libs/ /app/libs/
RUN pip install --no-cache-dir -e ./libs/common-utils

COPY apps-microservices/api-gateway .

EXPOSE 8500

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8500"]