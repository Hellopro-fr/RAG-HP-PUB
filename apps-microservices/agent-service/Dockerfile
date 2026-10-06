# apps-microservices/agent-service/Dockerfile
FROM python:3.11-slim

WORKDIR /app
ENV PYTHONPATH=/app

COPY apps-microservices/agent-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY apps-microservices/agent-service/app ./app
COPY apps-microservices/agent-service/main.py .

EXPOSE 8597
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8597"]
