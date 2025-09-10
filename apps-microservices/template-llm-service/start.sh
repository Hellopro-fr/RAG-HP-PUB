#!/bin/bash
#
# ==============================================================================
# SCRIPT DE DÉMARRAGE ADAPTATIF POUR LE SERVICE LLM
# ==============================================================================
#
# Ce script détecte le nombre de GPUs disponibles dans le conteneur et
# configure dynamiquement les variables d'environnement nécessaires pour que
# vLLM s'exécute en mode mono-GPU ou multi-GPU (parallélisme tensoriel).
#

# --- Étape 1: Détecter le nombre de GPUs disponibles ---
# On utilise nvidia-smi, l'outil standard de NVIDIA, pour compter les GPUs.
# La commande est conçue pour être robuste et ne retourner qu'un nombre.
NUM_GPUS=$(nvidia-smi --query-gpu=count --format=csv,noheader | head -n 1)

# Sécurité : vérifier si NUM_GPUS est bien un nombre.
if ! [[ "$NUM_GPUS" =~ ^[0-9]+$ ]]; then
    echo "ERREUR CRITIQUE: Impossible de déterminer le nombre de GPUs. Sortie de nvidia-smi invalide."
    exit 1
fi

echo "INFO: Détection du matériel... Nombre de GPUs trouvés: ${NUM_GPUS}"

# --- Étape 2: Configurer l'environnement en fonction du nombre de GPUs ---
# On utilise une structure de contrôle pour gérer les différents cas.

if [ "$NUM_GPUS" -ge 2 ]; then
  # --- Cas Multi-GPU (2 ou plus) ---
  echo "INFO: Configuration pour le mode Multi-GPU (Tensor Parallelism)."
  echo "INFO: Utilisation des GPUs 0 et 1."

  # On configure vLLM pour utiliser le parallélisme tensoriel sur 2 GPUs.
  export TENSOR_PARALLEL_SIZE=2

  # On s'assure que CUDA ne voit que les deux premiers GPUs, même s'il y en a plus.
  # C'est une bonne pratique pour un comportement déterministe.
  export CUDA_VISIBLE_DEVICES=0,1

elif [ "$NUM_GPUS" -eq 1 ]; then
  # --- Cas Mono-GPU ---
  echo "INFO: Configuration pour le mode Mono-GPU."
  echo "INFO: Utilisation du GPU 0."

  # On configure vLLM pour s'exécuter sur un seul GPU.
  export TENSOR_PARALLEL_SIZE=1

  # On s'assure que CUDA ne voit que le seul GPU disponible.
  export CUDA_VISIBLE_DEVICES=0

else
  # --- Cas d'Erreur (Aucun GPU) ---
  echo "ERREUR CRITIQUE: Aucun GPU NVIDIA n'a été trouvé dans ce conteneur."
  echo "ERREUR CRITIQUE: Le service template-llm-service ne peut pas démarrer."
  # On quitte avec un code d'erreur pour que Docker sache que le démarrage a échoué.
  exit 1
fi

echo "--------------------------------------------------------"
echo "Configuration finale :"
echo "  - TENSOR_PARALLEL_SIZE = ${TENSOR_PARALLEL_SIZE}"
echo "  - CUDA_VISIBLE_DEVICES = ${CUDA_VISIBLE_DEVICES}"
echo "--------------------------------------------------------"

# --- Étape 3: Lancer l'application Python ---
# 'exec' remplace le processus du script par le processus Python.
# C'est la manière propre de lancer le service principal, car les signaux
# (comme l'arrêt du conteneur) seront correctement transmis à l'application.
echo "INFO: Lancement de l'application principale du service LLM..."
exec python -u -m template_llm_service.main