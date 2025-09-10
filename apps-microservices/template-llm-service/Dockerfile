# Utiliser une base Python cohérente avec les autres services
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Définir le répertoire de travail
WORKDIR /app

# Définir le PYTHONPATH est crucial pour que les imports fonctionnent
ENV PYTHONPATH=/app

# On copie la lib partagée
COPY libs/common-utils /app/libs/common-utils
RUN pip install -e /app/libs/common-utils

# Copier uniquement le fichier des dépendances en utilisant le chemin complet depuis la racine
COPY apps-microservices/template-llm-service/requirements.txt .

# Installer les dépendances
RUN pip install --no-cache-dir -r requirements.txt

# Copier le code source de l'application en utilisant le chemin complet depuis la racine
COPY apps-microservices/template-llm-service/app /app/template_llm_service

# On copie le script de démarrage dans le conteneur.
COPY apps-microservices/template-llm-service/start.sh /app/start.sh

# On rend le script exécutable.
RUN chmod +x /app/start.sh

# La commande finale pour lancer le conteneur est maintenant notre script adaptatif.
CMD ["/app/start.sh"]