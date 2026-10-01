FROM python:3.10-slim
WORKDIR /app
ENV PYTHONPATH=/app

COPY apps-microservices/api-comparaison-texte/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY apps-microservices/api-comparaison-texte .

EXPOSE 8998
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port 8998 --proxy-headers --workers ${UVICORN_WORKERS:-2}"]
