FROM python:3.10-slim
# refresh OS packages of the final stage (fixable CVEs in base layers)
RUN apt-get update && apt-get -y upgrade && rm -rf /var/lib/apt/lists/*
WORKDIR /app
ENV PYTHONPATH=/app

COPY apps-microservices/api-comparaison-texte/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY apps-microservices/api-comparaison-texte .

EXPOSE 8998
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port 8998 --proxy-headers --workers ${UVICORN_WORKERS:-2}"]
