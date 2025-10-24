# ==============================================================================
# ÉTAPE 1 : BUILDER
# On part de l'image de développement officielle pour la version 0.10.0.
# Elle contient déjà CUDA, TensorRT, PyTorch, et toutes les dépendances
# de compilation correctement configurées.
# ==============================================================================
FROM nvcr.io/nvidia/tensorrt-llm/devel:1.2.0rc1 AS builder

WORKDIR /app

# L'image contient les outils, mais pas le code source. On clone donc le dépôt.
RUN git lfs install && \
    git clone -b release/1.2.0rc0.post1 https://github.com/NVIDIA/TensorRT-LLM.git

WORKDIR /app/TensorRT-LLM

# Lancer la compilation.
# Cette étape sera beaucoup plus rapide et fiable car l'environnement est déjà parfait.
# On n'a plus besoin de spécifier --trt_root car il est déjà dans le PATH.
RUN python3 scripts/build_wheel.py --clean --cuda_architectures 89

# Installer la wheel compilée pour la rendre disponible
RUN pip install /app/TensorRT-LLM/build/tensorrt_llm*.whl


# ==============================================================================
# ÉTAPE 2 : IMAGE FINALE
# On utilise toujours une image finale légère pour ne pas embarquer les 20 Go
# d'outils de développement.
# ==============================================================================
# CORRECTION : Utiliser une image runtime avec une version de CUDA compatible
# avec celle de l'image devel 1.2.0rc1 (qui utilise CUDA 12.5).
FROM nvidia/cuda:12.5.1-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive

# Copier les bibliothèques d'exécution de TensorRT depuis l'image de build.
# Dans l'image devel, elles sont dans /usr/local/tensorrt/lib
COPY --from=builder /usr/local/tensorrt/lib /usr/lib/
# S'assurer que le système trouve les bibliothèques partagées (.so)
RUN echo "/usr/lib" >> /etc/ld.so.conf.d/tensorrt.conf && ldconfig

# Installer les dépendances d'exécution système minimales
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.10 python3-pip git-lfs libopenmpi3 && \
    rm -rf /var/lib/apt/lists/*

RUN python3 -m pip install --upgrade pip && \
    ln -s /usr/bin/python3 /usr/bin/python

WORKDIR /app

# Copier la wheel compilée depuis l'étape de build
COPY --from=builder /app/TensorRT-LLM/build/tensorrt_llm*.whl .

# Installer la wheel et les autres dépendances Python
RUN pip install tensorrt_llm*.whl
RUN pip install huggingface_hub torch

# Copier votre script
COPY model-optimizer/build_trt_engine.py /app/model-optimizer/build_trt_engine.py