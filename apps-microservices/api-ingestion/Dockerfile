FROM python:3.10-slim
WORKDIR /app

# Étape 1: Définir le PYTHONPATH
ENV PYTHONPATH=/app

# Étape 2: Installer les dépendances
# Copie et installe la librairie partagée
COPY libs/common-utils /app/libs/common-utils
RUN pip install -e /app/libs/common-utils

# Copie et installe les requirements spécifiques au service
COPY apps-microservices/api-ingestion/requirements.txt .
RUN pip install -r requirements.txt

# Étape 3: Copier le code source ET les scripts
# On copie le code de l'application dans son propre dossier nommé
COPY apps-microservices/api-ingestion .

# Étape 4: Rendre les scripts exécutables
RUN chmod +x init.sh
RUN chmod +x run.sh

# Étape 5: Exécuter le script d'initialisation (si nécessaire)
# Cette étape est exécutée PENDANT la construction de l'image
RUN ./init.sh

# Étape 6: Exposer le port et définir la commande de lancement
EXPOSE 8509
# La commande qui sera exécutée AU DÉMARRAGE du conteneur
CMD ["./run.sh"]