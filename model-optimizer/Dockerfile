# Ce conteneur a pour seul but de convertir les modèles PyTorch en ONNX.
# Il contient toutes les dépendances lourdes.
FROM python:3.10-slim

WORKDIR /builder

# Installer les dépendances de conversion
COPY model-optimizer/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copier les scripts de conversion
COPY model-optimizer/export_embedding_to_onnx.py .
COPY model-optimizer/export_reranker_to_onnx.py .

# Le point d'entrée est laissé vide. La commande sera spécifiée dans docker-compose.