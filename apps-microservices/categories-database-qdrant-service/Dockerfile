FROM python:3.10-slim
WORKDIR /app

# Étape 1: Définir le PYTHONPATH.
# Dit à Python de toujours chercher les modules à partir du dossier /app.
ENV PYTHONPATH=/app

# Étape 2: Installer les dépendances
# On copie la lib partagée
COPY libs/common-utils /app/libs/common-utils
RUN pip install -e /app/libs/common-utils
# On copie les requirements du service
# Étape 1: Définir le PYTHONPATH.
# Dit à Python de toujours chercher les modules à partir du dossier /app.
ENV PYTHONPATH=/app

# Étape 2: Installer les dépendances
# On copie la lib partagée
COPY libs/common-utils /app/libs/common-utils
RUN pip install -e /app/libs/common-utils
# On copie les requirements du service
COPY apps-microservices/categories-database-qdrant-service/requirements.txt .
RUN pip install -r requirements.txt

# Étape 3: Copier le code source
# On copie le CONTENU du dossier app local directement dans le WORKDIR (/app)
COPY apps-microservices/categories-database-qdrant-service/app/ /app/categories_database_qdrant_service

# Étape 4: Définir la commande
# On peut maintenant exécuter le script directement, les imports fonctionneront grâce au PYTHONPATH.
CMD ["python", "-u", "-m", "categories_database_qdrant_service.main"]