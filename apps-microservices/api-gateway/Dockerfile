# apps-microservices/api-ingestion/Dockerfile

FROM python:3.10-slim
WORKDIR /app

ENV PYTHONPATH=/app

COPY apps-microservices/api-gateway/requirements.txt .
RUN pip install -r requirements.txt

COPY apps-microservices/api-ingestion .

EXPOSE 8500

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8500"]