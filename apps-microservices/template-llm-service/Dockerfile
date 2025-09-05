# Utiliser une base Python cohérente avec les autres services
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Définir le répertoire de travail
WORKDIR /app

# Définir le PYTHONPATH est crucial pour que les imports fonctionnent
ENV PYTHONPATH=/app

# --- CORRECTION ICI ---
# Copier uniquement le fichier des dépendances en utilisant le chemin complet depuis la racine
COPY apps-microservices/template-llm-service/requirements.txt .
# --- FIN DE LA CORRECTION ---

# Installer les dépendances
RUN pip install --no-cache-dir -r requirements.txt

# --- CORRECTION ICI ---
# Copier le code source de l'application en utilisant le chemin complet depuis la racine
COPY apps-microservices/template-llm-service/app /app/template_llm_service
# --- FIN DE LA CORRECTION ---

# La commande finale pour lancer le worker
CMD ["python", "-u", "-m", "template_llm_service.main"]