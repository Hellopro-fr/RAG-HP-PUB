# apps-microservices/api-classification/Dockerfile
FROM python:3.10-slim

# Étape 1: Définir le PYTHONPATH pour que les imports fonctionnent
ENV PYTHONPATH=/app

# Définition du répertoire de travail
WORKDIR /app

# Ensuite, on copie et installe les requirements spécifiques à ce service
COPY apps-microservices/api-classification/requirements.txt .
RUN pip install -r requirements.txt

# Étape 3: Copier le code source de manière propre
# On copie le code de l'application dans son propre dossier NOMMÉ et UNIQUE
COPY apps-microservices/api-classification .

# Étape 4: Exposer le port
EXPOSE 8566


# Commande par défaut optimisée pour VM GCP
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8566"]