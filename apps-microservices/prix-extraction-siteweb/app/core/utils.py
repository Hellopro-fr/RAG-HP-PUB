"""
Fonctions utilitaires pour le service prix-extraction-siteweb
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


def get_tracking_filepath(
    id_categorie: str, 
    prefix: str = "prix-extraction-siteweb",
    base_dir: str = "tracking"
) -> str:
    """
    Génère le chemin du fichier de tracking
    
    Args:
        id_categorie: ID de la catégorie
        prefix: Préfixe du nom de fichier
        base_dir: Répertoire de base pour les fichiers de tracking
        
    Returns:
        Chemin complet du fichier de tracking
    """
    year = datetime.now().strftime("%Y")
    month = datetime.now().strftime("%m")
    timestamp = datetime.now().strftime("%Y-%m-%d-%H-%M")
    
    directory = f"{base_dir}/{year}/{month}/"
    ensure_directory(directory)
    
    filename = f"{timestamp}-tracking-{prefix}-{id_categorie}.txt"
    
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
