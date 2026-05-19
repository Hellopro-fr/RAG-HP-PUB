"""
Fonctions utilitaires pour prix-caracterisation (JSON extraction, tracking, prompt loader).
"""
import json
import re
import os
from pathlib import Path
from typing import Dict, Any, Optional
import logging
from datetime import datetime

from app.core.api_client import HelloProAPIClient

logger = logging.getLogger(__name__)


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


def extract_json_from_text(text: str) -> Optional[Any]:
    """
    Extrait et parse un JSON depuis du texte libre (réponse LLM).
    Tente une réparation des guillemets non-échappés (_fix_unescaped_quotes) en fallback.
    """
    if text is None:
        return None
    text = re.sub(r'\s+', ' ', text)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    patterns = [
        r'(\{.*\}|\[.*\])',
        r'\[.*\]',
        r'\{.*\}',
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


def ensure_directory(path: str) -> bool:
    try:
        Path(path).mkdir(parents=True, exist_ok=True)
        return True
    except Exception as e:
        logger.error(f"Erreur création répertoire {path}: {e}")
        return False


def save_json_file(filepath: str, data: Any) -> bool:
    try:
        ensure_directory(os.path.dirname(filepath))
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.error(f"Erreur sauvegarde {filepath}: {e}")
        return False


def load_json_file(filepath: str) -> Optional[Any]:
    try:
        if not os.path.exists(filepath):
            return None
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Erreur chargement {filepath}: {e}")
        return None


def check_stopper(id_categorie: str, stopper_file: str = "fichiers/stopper.json") -> bool:
    """Vérifie si la catégorie doit être stoppée manuellement."""
    try:
        if not os.path.exists(stopper_file):
            save_json_file(stopper_file, [])
            return False
        stopper_list = load_json_file(stopper_file) or []
        if id_categorie in stopper_list:
            stopper_list.remove(id_categorie)
            save_json_file(stopper_file, stopper_list)
            logger.warning(f"Catégorie {id_categorie} stoppée manuellement")
            return True
        return False
    except Exception as e:
        logger.error(f"Erreur check_stopper: {e}")
        return False


def get_tracking_filepath(
    id_categorie: str,
    prefix: str = "prix-caracterisation",
    base_dir: str = "tracking",
) -> str:
    year = datetime.now().strftime("%Y")
    month = datetime.now().strftime("%m")
    timestamp = datetime.now().strftime("%Y-%m-%d-%H-%M")
    directory = f"{base_dir}/{year}/{month}/"
    ensure_directory(directory)
    filename = f"{timestamp}-tracking-{prefix}-{id_categorie}.txt"
    return os.path.join(directory, filename)


def write_log(filepath: str, message: str):
    try:
        ensure_directory(os.path.dirname(filepath))
        with open(filepath, 'a', encoding='utf-8') as f:
            f.write(f"{message}\n")
    except Exception as e:
        logger.error(f"Erreur écriture log {filepath}: {e}")


async def get_prompt(id_prompt: str) -> Dict[str, Any]:
    """Charge un prompt depuis action_prompt_chatgpt via l'API BO."""
    api_client = HelloProAPIClient()
    try:
        prompt_config = await api_client.post(
            "prompt",
            "info",
            "get",
            {"id_prompt": id_prompt},
        )
    finally:
        await api_client.close()
    return prompt_config


def to_json_string(data: Any) -> str:
    try:
        return json.dumps(data, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Erreur conversion JSON: {e}")
        return "{}"
