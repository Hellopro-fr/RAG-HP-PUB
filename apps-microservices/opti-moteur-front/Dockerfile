# apps-microservices/opti-moteur-front/Dockerfile
FROM python:3.10-slim
WORKDIR /app

ENV PYTHONPATH=/app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install dependencies
COPY apps-microservices/opti-moteur-front/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app source
COPY apps-microservices/opti-moteur-front .

EXPOSE 8570

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8570"]
