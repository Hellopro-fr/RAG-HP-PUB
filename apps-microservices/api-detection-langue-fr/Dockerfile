FROM python:3.10-slim
WORKDIR /app

# Étape 1: Définir le PYTHONPATH pour que les imports fonctionnent
ENV PYTHONPATH=/app

# Étape 2: Installer les dépendances système pour Firefox/Camoufox et Chromium (fallback)
# Camoufox is a stealth Firefox — needs GTK3, dbus, etc.
# Chromium kept as fallback via CAMOUFOX_ENABLED=false
RUN apt-get update && apt-get install -y \
    libgtk-3-0 libdbus-glib-1-2 libasound2t64 libxcomposite1 libxdamage1 \
    libxrandr2 libpango-1.0-0 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
    --no-install-recommends && rm -rf /var/lib/apt/lists/*

# Étape 3: Installer les dépendances Python
COPY apps-microservices/api-detection-langue-fr/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Installer Playwright Chromium (fallback when CAMOUFOX_ENABLED=false)
RUN python -m playwright install --with-deps chromium

# Télécharger le navigateur Camoufox (stealth Firefox, ~200MB)
RUN python -m camoufox fetch

# Étape 4: Copier le code source
COPY apps-microservices/api-detection-langue-fr .

# Étape 5: Exposer le port
EXPOSE 8999

# Étape 6: Lancement
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8999", \
     "--proxy-headers", "--timeout-keep-alive", "300", \
     "--limit-concurrency", "50"]