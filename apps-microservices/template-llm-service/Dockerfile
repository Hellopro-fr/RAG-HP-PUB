# Utiliser la même base que vos autres services pour la cohérence
FROM python:3.11-slim

# Définir le répertoire de travail
WORKDIR /app

# Définir le PYTHONPATH pour que les imports fonctionnent correctement avec la commande CMD
ENV PYTHONPATH=/app

# Copier uniquement le fichier des dépendances pour optimiser le cache Docker
COPY template-llm-service/requirements.txt .

# Installer les dépendances directement dans l'environnement du conteneur
# (Pas de .venv !)
RUN pip install --no-cache-dir -r requirements.txt

# Copier le code source de l'application dans un sous-répertoire nommé
# pour garder la racine propre.
COPY template-llm-service/app/ /app/template_llm_service/

# La commande pour lancer le worker RabbitMQ.
# -u : pour un output non bufferisé (voir les logs en temps réel)
# -m : pour exécuter le module comme un script
CMD ["python", "-u", "-m", "template_llm_service.main"]