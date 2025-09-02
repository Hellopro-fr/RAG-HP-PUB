# Utiliser une base Python cohérente avec les autres services
FROM python:3.11-slim

# Définir le répertoire de travail
WORKDIR /app

# Définir le PYTHONPATH est crucial pour que les imports fonctionnent
ENV PYTHONPATH=/app

# Copier les requirements d'abord pour optimiser le cache Docker
COPY template-llm-service/requirements.txt .

# Installer les dépendances
RUN pip install --no-cache-dir -r requirements.txt

# Copier le code source de l'application dans un sous-répertoire nommé
# C'est la convention utilisée par vos collègues
COPY template-llm-service/app /app/template_llm_service

# La commande finale pour lancer le worker
CMD ["python", "-u", "-m", "template_llm_service.main"]