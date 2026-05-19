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


def _fix_unescaped_quotes(text: str) -> str:
    """
    Répare les guillemets non-échappés à l'intérieur des valeurs JSON produites par un LLM.
    Tracke l'état clé/valeur pour distinguer une vraie fin de string d'un faux positif
    type "il a dit "bonjour", puis...". Normalise les guillemets typographiques en amont.
    """
    text = text.replace("“", '"').replace("”", '"')

    result = []
    n = len(text)
    i = 0
    in_string = False
    expecting_value = False  # True après `:` ou `[` -> on attend une valeur

    while i < n:
        ch = text[i]

        if not in_string:
            result.append(ch)
            if ch == ':':
                expecting_value = True
            elif ch == '[':
                expecting_value = True
            elif ch in ('{', ','):
                expecting_value = False
            elif ch == '"':
                in_string = True
            i += 1
            continue

        if ch == '\\':
            result.append(ch)
            i += 1
            if i < n:
                result.append(text[i])
                i += 1
            continue

        if ch == '"':
            j = i + 1
            while j < n and text[j].isspace():
                j += 1
            nxt = text[j] if j < n else ''

            if expecting_value:
                is_end = nxt in (',', '}', ']') or j >= n
            else:
                is_end = (nxt == ':')

            if is_end:
                result.append(ch)
                in_string = False
                if expecting_value:
                    expecting_value = False
            else:
                result.append('\\"')
            i += 1
            continue

        result.append(ch)
        i += 1

    return ''.join(result)


def extract_json_from_text(text: str) -> Optional[Dict[str, Any]]:
    """
    Extrait et parse JSON d'une chaîne de texte.
    Tente une réparation des guillemets non-échappés (_fix_unescaped_quotes) en fallback.
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
                try:
                    fixed = _fix_unescaped_quotes(matches.group(0))
                    return json.loads(fixed)
                except json.JSONDecodeError:
                    continue

    # Dernière tentative: nettoyer le début et la fin
    trimmed = re.sub(r'^[^{]*|[^}]*$', '', text)
    try:
        return json.loads(trimmed)
    except json.JSONDecodeError:
        try:
            fixed = _fix_unescaped_quotes(trimmed)
            return json.loads(fixed)
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
