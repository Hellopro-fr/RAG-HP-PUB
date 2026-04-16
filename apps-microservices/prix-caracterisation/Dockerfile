# prix-caracterisation Dockerfile
# Consumer RabbitMQ dédié à la caractérisation des prix Milvus (collection `prix`) — table _cppi.

FROM python:3.10-slim

WORKDIR /app

ENV PYTHONPATH=/app

COPY libs/common-utils /app/libs/common-utils
RUN pip install --no-cache-dir -e /app/libs/common-utils

COPY apps-microservices/prix-caracterisation/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY apps-microservices/prix-caracterisation/app ./app
COPY apps-microservices/prix-caracterisation/main.py .

CMD ["python", "main.py"]
