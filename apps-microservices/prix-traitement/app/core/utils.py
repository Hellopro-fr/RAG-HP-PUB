"""
Fonctions utilitaires pour le service prix-traitement
"""
import json
import re
from typing import Dict, Any, Optional
import logging

from app.core.api_client import HelloProAPIClient

logger = logging.getLogger(__name__)


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
