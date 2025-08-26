# ============================================================
# Dockerfile : Python 3.10 + PyTorch CUDA (cu128) sur image slim
# ============================================================
FROM python:3.10-slim-bookworm
 
# ---------- OS deps minimales ----------
# - ca-certificates/curl: fetch/https
# - git: au cas où (pip -e, répos privés)
# - tini: PID 1 sain (signals, zombies)
# - libgomp1: openmp (certains wheels y tiennent)
# - build-essential: optionnel (souvent inutile mais pratique si une lib compile)
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates curl git tini libgomp1 \
      build-essential \
&& rm -rf /var/lib/apt/lists/*
 
# ---------- ENV de base ----------
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TOKENIZERS_PARALLELISM=false \
    HF_HOME=/cache/huggingface \
    PYTHONPATH=/app
 
# Dossier de travail
WORKDIR /app
 
# ============================================================
# OPTION A (RECO) — Installer PyTorch GPU (CUDA 12.8) via l’index PyTorch
#   - Ces roues embarquent les libs CUDA runtime nécessaires.
#   - Nécessite sur l'hôte : driver NVIDIA + nvidia-container-toolkit
# ============================================================
# (si cu128 non dispo, repli sur cu126)
RUN python -m pip install --upgrade pip && \
    (python -m pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128 \
     || python -m pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu126)
 
 
# ---------- Installer ta lib partagée en mode editable ----------
# (adapter le chemin si besoin; on maximise le cache en copiant tôt)
COPY libs/common-utils /app/libs/common-utils
RUN python -m pip install -e /app/libs/common-utils
 
# ---------- Installer les requirements du service ----------
# IMPORTANT: ne mets pas 'torch' dans ce fichier (on l'a déjà installé en GPU)
COPY apps-microservices/embedding-service/requirements.txt /app/requirements.txt
RUN pip install sentence-transformers transformers==4.30.2 tokenizers==0.13.3 sentencepiece protobuf==3.20.3 huggingface-hub==0.19.4 torch torchvision torchaudio --extra-index-url https://download.pytorch.org/whl/cu121
RUN python -m pip install -q -r /app/requirements.txt
 
# ---------- Copier le code de l'app ----------
COPY apps-microservices/embedding-service/app/ /app/embedding_service
 
# ---------- Entrypoint PID 1 propre ----------
ENTRYPOINT ["/usr/bin/tini", "--"]
 
# ---------- Commande ----------
CMD ["python", "-u", "-m", "embedding_service.main"]