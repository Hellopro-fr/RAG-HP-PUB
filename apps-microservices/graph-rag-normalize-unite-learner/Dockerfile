FROM python:3.10-slim

WORKDIR /app
ENV PYTHONPATH=/app

COPY apps-microservices/graph-rag-normalize-unite-learner/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Shared lib (metrics Prometheus) — pas de gRPC ici
COPY libs /app/libs
RUN pip install -e /app/libs/common-utils

COPY apps-microservices/graph-rag-normalize-unite-learner/app ./app

# REST (déclenchement manuel) 8566 + Prometheus 8567
EXPOSE 8566 8567
CMD ["python", "-m", "app.main"]
