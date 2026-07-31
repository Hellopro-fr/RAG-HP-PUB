# QC-fabricant-reference — extraction marque / reference (etape PSI 16)
# Ni gRPC ni protobuf : ce service n'appelle qu'une API REST et un LLM.

FROM python:3.10-slim

WORKDIR /app

ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1

# Bibliotheque partagee (DLQPropertiesAsync) — n'exige que redis
COPY libs/common-utils /app/libs/common-utils
RUN pip install --no-cache-dir -e /app/libs/common-utils

COPY apps-microservices/QC-fabricant-reference/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY apps-microservices/QC-fabricant-reference/app ./app
COPY apps-microservices/QC-fabricant-reference/main.py .

RUN mkdir -p /app/tracking /app/fichiers

# Le service tourne en root, comme TOUS les autres services QC (QC-caracterisation,
# QC-generation-*, prix-*) : /app/tracking est un bind mount vers un repertoire de l'hote
# appartenant a root. Un USER non-root ici ne peut pas y ecrire — le chown de l'image
# porte sur le dossier de l'image, que le montage remplace au demarrage
# (symptome : "Permission denied: 'tracking/2026'", aucun fichier de tracking ecrit).
#
# Pour repasser non-root il faudrait un uid FIXE cote image ET cote hote :
#   RUN useradd --uid 1000 --create-home --shell /usr/sbin/nologin appuser && chown -R appuser /app
#   USER appuser
#   + sur l'hote : chown -R 1000:1000 /mnt/data/docker/images/generation-question-caracteristiques/qc-fabricant-reference
# A faire pour toute la plateforme d'un coup, pas pour ce seul service.

CMD ["python", "main.py"]
