FROM python:3.10-slim
WORKDIR /app

COPY apps-microservices/ingestion-service/requirements.txt .
RUN pip install -r requirements.txt

# On copie le dossier app entier qui contient notre logique
COPY apps-microservices/ingestion-service/app /app/app

# La commande de lancement pointe maintenant vers le script dans le dossier app
CMD ["python", "-u", "-m", "app.main"]
