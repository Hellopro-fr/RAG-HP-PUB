"""
Fonctions utilitaires pour le service prix-traitement
"""
import json
import os
import re
import time
from datetime import datetime
from typing import Dict, Any, Optional
import logging

from app.core.api_client import HelloProAPIClient

logger = logging.getLogger(__name__)


def ensure_directory(directory: str) -> None:
    try:
        os.makedirs(directory, exist_ok=True)
    except Exception as e:
        logger.error(f"Erreur création dossier {directory}: {e}")


def get_tracking_filepath(
    id_categorie: str,
    prefix: str = "prix-traitement",
    base_dir: str = "tracking",
) -> str:
    """
    Retourne le chemin d'un fichier tracking pour une catégorie.
    Format : {base_dir}/{year}/{month}/{timestamp}-tracking-{prefix}-{id_categorie}.txt
    """
    year = datetime.now().strftime("%Y")
    month = datetime.now().strftime("%m")
    timestamp = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
    directory = f"{base_dir}/{year}/{month}/"
    ensure_directory(directory)
    filename = f"{timestamp}-tracking-{prefix}-{id_categorie}.txt"
    return os.path.join(directory, filename)


def write_log(filepath: str, message: str) -> None:
    try:
        ensure_directory(os.path.dirname(filepath))
        with open(filepath, 'a', encoding='utf-8') as f:
            f.write(f"{message}\n")
    except Exception as e:
        logger.error(f"Erreur écriture log {filepath}: {e}")


def extract_json_from_text(text: str) -> Optional[Dict[str, Any]]:
    """
    Extrait et parse JSON d'une chaîne de texte
    """
    # Normaliser les espaces
    text = re.sub(r'\s+', ' ', text)
    
    try:
        # Tentative de parsing direct
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    
    # Recherche de patterns JSON
    patterns = [
        r'(\{.*\}|\[.*\])', # Object ou Array
        r'\[.*\]',  # Array
        r'\{.*\}',  # Object
    ]
    
    for pattern in patterns:
        matches = re.search(pattern, text, re.DOTALL | re.MULTILINE)
        if matches:
            try:
                return json.loads(matches.group(0))
            except json.JSONDecodeError:
                continue
    
    # Dernière tentative: nettoyer le début et la fin
    trimmed = re.sub(r'^[^{]*|[^}]*$', '', text)
    try:
        return json.loads(trimmed)
    except json.JSONDecodeError:
        logger.error(f"Impossible d'extraire JSON de: {text[:200]}")
        return None


async def get_prompt(id_prompt: str) -> Dict[str, Any]:
    # Récupérer le prompt
    api_client = HelloProAPIClient()
    prompt_config = await api_client.post(
        "prompt",
        "info",
        "get",
        {"id_prompt": id_prompt}
    )
    return prompt_config


# Cache en mémoire pour les prompts (évite un appel HTTP à chaque requête)
_prompt_cache: Dict[str, Any] = {}
PROMPT_CACHE_TTL = 300  # 5 minutes


async def get_prompt_cached(id_prompt: str) -> Optional[Dict[str, Any]]:
    """
    Récupère un prompt avec cache en mémoire (TTL 300s).
    Évite de refaire un appel HTTP si le prompt a déjà été chargé récemment.
    """
    now = time.time()
    if id_prompt in _prompt_cache:
        cached, ts = _prompt_cache[id_prompt]
        if now - ts < PROMPT_CACHE_TTL:
            logger.info(f"Prompt id={id_prompt} servi depuis le cache")
            return cached

    result = await get_prompt(id_prompt)
    if result is not None:
        _prompt_cache[id_prompt] = (result, now)
    return result
