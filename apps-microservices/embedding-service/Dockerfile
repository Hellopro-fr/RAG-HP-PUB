FROM python:3.10-slim
WORKDIR /app

COPY apps-microservices/embedding-service/requirements.txt .
RUN pip install -r requirements.txt
COPY apps-microservices/embedding-service/app /app/app

CMD ["python", "-u", "-m", "app.main"]
