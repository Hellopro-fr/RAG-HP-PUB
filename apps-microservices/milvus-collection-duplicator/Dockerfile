# apps-microservices/milvus-collection-duplicator/Dockerfile

FROM python:3.10-slim
WORKDIR /app

# Définir le PYTHONPATH pour que les imports fonctionnent
ENV PYTHONPATH=/app

# Installer les dépendances
COPY apps-microservices/milvus-collection-duplicator/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copier le code source
COPY apps-microservices/milvus-collection-duplicator .

# Exposer le port
EXPOSE 8521

# Lancer le service
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8521"]
