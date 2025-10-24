# Étape 1: Base avec l'environnement CUDA et les dépendances de build
FROM nvidia/cuda:12.1.1-devel-ubuntu22.04 AS builder

ENV DEBIAN_FRONTEND=noninteractive

# Installation des dépendances système requises pour la compilation de TensorRT-LLM
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.10 python3.10-dev python3.10-venv python3-pip git git-lfs openmpi-bin libopenmpi-dev build-essential cmake \
    && rm -rf /var/lib/apt/lists/*

# Mettre à jour pip et créer un lien symbolique pour python -> python3
RUN python3 -m pip install --upgrade pip && \
    ln -s /usr/bin/python3 /usr/bin/python

WORKDIR /app

# Cloner le dépôt TensorRT-LLM depuis GitHub
# On utilise une branche de release spécifique pour la stabilité
RUN git lfs install && \
    git clone -b v0.10.0 https://github.com/NVIDIA/TensorRT-LLM.git

WORKDIR /app/TensorRT-LLM

# Installer les dépendances Python requises par TensorRT-LLM
RUN pip install -r requirements.txt

# Lancer la compilation et l'installation de la bibliothèque TensorRT-LLM
# Cette étape est longue
RUN python3 scripts/build_wheel.py --clean --trt_root /usr/local/cuda
RUN pip install /app/TensorRT-LLM/build/tensorrt_llm*.whl

# --- Image Finale ---
# On crée une image finale plus légère en copiant uniquement les artefacts nécessaires
FROM nvidia/cuda:12.1.1-devel-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive

# Installer uniquement les dépendances d'exécution
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.10 python3-pip git git-lfs && \
    rm -rf /var/lib/apt/lists/*

RUN python3 -m pip install --upgrade pip && \
    ln -s /usr/bin/python3 /usr/bin/python

WORKDIR /app

# Copier la bibliothèque TensorRT-LLM compilée depuis l'étape de build
COPY --from=builder /app/TensorRT-LLM/build/tensorrt_llm*.whl .

# Installer la wheel et les autres dépendances Python
RUN pip install tensorrt_llm*.whl
RUN pip install huggingface_hub torch

# Copier le script de compilation du modèle
COPY model-optimizer/build_trt_engine.py /app/model-optimizer/build_trt_engine.py
