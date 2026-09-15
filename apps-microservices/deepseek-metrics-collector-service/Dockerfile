# Utiliser une base Python légère
FROM python:3.11-slim
# refresh OS packages of the final stage (fixable CVEs in base layers)
RUN apt-get update && apt-get -y upgrade && rm -rf /var/lib/apt/lists/*

# Définir le répertoire de travail
WORKDIR /app

# Définir le PYTHONPATH est crucial pour que les imports fonctionnent
ENV PYTHONPATH=/app

# On copie la lib partagée
COPY libs/common-utils /app/libs/common-utils
RUN pip install -e /app/libs/common-utils

# Copier les dépendances et les installer
COPY ./apps-microservices/deepseek-metrics-collector-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copier le code source de l'application
COPY ./apps-microservices/deepseek-metrics-collector-service/app /app

# Définir la commande pour lancer le service
CMD ["python", "-u", "main.py"]