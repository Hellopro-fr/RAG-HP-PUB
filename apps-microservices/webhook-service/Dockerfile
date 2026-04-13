FROM python:3.10-slim
WORKDIR /app

# PYTHONPATH pour que les imports webhook_service.* fonctionnent
ENV PYTHONPATH=/app

# Installer la lib partagée
COPY libs/common-utils /app/libs/common-utils
RUN pip install -e /app/libs/common-utils

# Installer les dépendances du service
COPY apps-microservices/webhook-service/requirements.txt .
RUN pip install -r requirements.txt

# Copier le code source
COPY apps-microservices/webhook-service/app/ /app/webhook_service/

# Démarrer le service
CMD ["python", "-u", "-m", "webhook_service.main"]
