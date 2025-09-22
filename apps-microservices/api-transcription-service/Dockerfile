FROM python:3.10-slim
WORKDIR /app

# Étape 1: Définir le PYTHONPATH pour que les imports fonctionnent
ENV PYTHONPATH=/app

COPY apps-microservices/api-transcription-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Étape 3: Copier le code source de manière propre
# On copie le code de l'application dans son propre dossier NOMMÉ et UNIQUE
COPY apps-microservices/api-transcription-service/ /app/

# Étape 4: Exposer le port
EXPOSE 8515

# Étape 5: Définir la commande de lancement directement
# On lance Uvicorn en lui disant de trouver le module 'main' dans le paquet 'api_ingestion_service'
# Le port est défini dynamiquement par la variable $PORT de Render, avec une valeur par défaut de 8509.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8515"]