"""
Fonctions utilitaires pour la génération de questions et caractéristiques
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


def extract_json_from_text(text: str) -> Optional[Dict[str, Any]]:
    """
    Extrait et parse le premier JSON valide d'une réponse LLM.

    Tolère :
      - Fences markdown ```json ... ``` ou ``` ... ```
      - Texte explicatif avant/après le JSON
      - Duplications (`"[] [other JSON]"` → retourne le premier)
      - Guillemets non échappés (fallback _fix_unescaped_quotes)
      - JSON vide `[]` ou `{}` (cas "aucun résultat")

    Retourne None uniquement si aucun JSON exploitable n'est trouvé.
    """
    if not text:
        return None

    # 1. Strip des fences markdown courantes (```json ... ``` ou ``` ... ```)
    text = re.sub(r'```(?:json|JSON)?\s*', '', text)
    text = text.replace('```', '')
    text = text.strip()

    if not text:
        return None

    # 2. Tentative directe (cas LLM bien discipliné)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 3. Balayage : trouve le 1er { ou [, tente raw_decode depuis là.
    #    Fallback _fix_unescaped_quotes si guillemets non échappés.
    #    Avance d'un cran si échec et retente.
    decoder = json.JSONDecoder()
    n = len(text)
    for start in range(n):
        if text[start] in '{[':
            sub = text[start:]
            try:
                obj, _ = decoder.raw_decode(sub)
                return obj
            except json.JSONDecodeError:
                try:
                    fixed = _fix_unescaped_quotes(sub)
                    obj, _ = decoder.raw_decode(fixed)
                    return obj
                except json.JSONDecodeError:
                    continue

    logger.error(f"Impossible d'extraire JSON de: {text[:200]}")
    return None


def ensure_directory(path: str) -> bool:
    """Crée un répertoire s'il n'existe pas"""
    try:
        Path(path).mkdir(parents=True, exist_ok=True)
        return True
    except Exception as e:
        logger.error(f"Erreur lors de la création du répertoire {path}: {e}")
        return False


def save_json_file(filepath: str, data: Any) -> bool:
    """Sauvegarde des données en JSON"""
    try:
        ensure_directory(os.path.dirname(filepath))
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.error(f"Erreur lors de la sauvegarde de {filepath}: {e}")
        return False


def load_json_file(filepath: str) -> Optional[Any]:
    """Charge un fichier JSON"""
    try:
        if not os.path.exists(filepath):
            return None
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Erreur lors du chargement de {filepath}: {e}")
        return None

# Vérifier le stopper manuel
def check_stopper(id_categorie: str, stopper_file: str = "fichiers/stopper.json") -> bool:
    """
    Vérifie si la catégorie doit être stoppée
    Retourne True si le processus doit s'arrêter
    """
    try:
        if not os.path.exists(stopper_file):
            save_json_file(stopper_file, [])
            return False
        
        stopper_list = load_json_file(stopper_file) or []
        
        if id_categorie in stopper_list:
            # Retirer l'ID de la liste
            stopper_list.remove(id_categorie)
            save_json_file(stopper_file, stopper_list)
            logger.warning(f"Catégorie {id_categorie} stoppée manuellement")
            return True
        
        return False
    except Exception as e:
        logger.error(f"Erreur lors de la vérification du stopper: {e}")
        return False


def filter_response_keys(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Filtre les clés qui correspondent au pattern 'reponse-\\d+'
    """
    return {
        key: value 
        for key, value in data.items() 
        if re.match(r'^reponse-\d+$', key)
    }


def get_result_path(id_categorie: str, base_dir: str = "data") -> str:
    """Génère le chemin pour les résultats"""
    year = datetime.now().strftime("%Y")
    month = datetime.now().strftime("%m")
    return f"{base_dir}/{year}/{month}/{id_categorie}/"

def get_tracking_filepath(
    id_categorie: str, 
    prefix: str = "question",
    base_dir: str = "tracking"
) -> str:
    """
    Génère le chemin du fichier de tracking
    
    Args:
        id_categorie: ID de la catégorie
        prefix: Préfixe du nom de fichier (question, caracteristique, etc.)
        base_dir: Répertoire de base pour les fichiers de tracking
        
    Returns:
        Chemin complet du fichier de tracking
    """
    year = datetime.now().strftime("%Y")
    month = datetime.now().strftime("%m")
    timestamp = datetime.now().strftime("%Y-%m-%d-%H-%M")
    
    directory = f"{base_dir}/{year}/{month}/"
    ensure_directory(directory)
    
    filename = f"{timestamp}-tracking-generation-{prefix}-gemini-{id_categorie}.txt"
    
    return os.path.join(directory, filename)

def write_log(filepath: str, message: str):
    """Écrit un message dans un fichier de log"""
    try:
        ensure_directory(os.path.dirname(filepath))
        with open(filepath, 'a', encoding='utf-8') as f:
            f.write(f"{message}\n")
    except Exception as e:
        logger.error(f"Erreur lors de l'écriture du log: {e}")

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

def to_json_string(data: Any) -> str:
    """
    Convertit des données en chaîne JSON formatée
    
    Args:
        data: Données à convertir
        
    Returns:
        Chaîne JSON formatée
    """
    try:
        return json.dumps(data, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Erreur lors de la conversion en JSON: {e}")
        return "{}"