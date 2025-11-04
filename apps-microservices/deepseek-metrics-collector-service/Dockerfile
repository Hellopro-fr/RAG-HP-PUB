# Utiliser une base Python légère
FROM python:3.11-slim

# Définir le répertoire de travail
WORKDIR /app

# Copier les dépendances et les installer
COPY ./apps-microservices/deepseek-metrics-collector-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copier le code source de l'application
COPY ./apps-microservices/deepseek-metrics-collector-service/app /app

# Définir la commande pour lancer le service
CMD ["python", "-u", "main.py"]