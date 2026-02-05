# QC-tracking-service

FROM python:3.10-slim

WORKDIR /app

COPY apps-microservices/QC-tracking-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY apps-microservices/QC-tracking-service/app ./app
COPY apps-microservices/QC-tracking-service/main.py .
COPY apps-microservices/QC-tracking-service/static ./static

EXPOSE 8590

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8590"]
