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


def process_product_data_for_embedding(
    prix_data: dict,
    id_categorie: str = "",
    source: str = "produits",
    database: str = "qdrant",
    origin: str = "prix-extraction"
) -> dict:
    """
    Formate et prépare les données de prix d'un item avant publication
    dans la queue ready_for_embedding (collection PRIX).

    Le texte à embedder est structuré avec des libellés explicites pour maximiser
    la pertinence des recherches RAG vectorielles sur les questions/réponses acheteur.

    Args:
        prix_data   : Dictionnaire de données de prix (ProduitPrixPayload.dict() ou équivalent)
        id_categorie: ID de la catégorie de traitement
        source      : Source de l'item (produits par défaut pour ce service)
        database    : Base vectorielle cible (défaut: qdrant)
        origin      : Origine du message pour le tracking

    Returns:
        Dictionnaire prêt à être publié sur l'exchange d'embedding.
        Structure compatible avec le pipeline embedding de la collection PRIX.
    """
    from common_utils.autres.CollectionName import CollectionName

    if not isinstance(prix_data, dict):
        raise ValueError("prix_data doit être un dictionnaire.")

    def _v(key: str) -> str:
        """Retourne la valeur sous forme de chaîne propre, ou chaîne vide."""
        val = prix_data.get(key)
        return str(val).strip() if val else ""

    # Construire le texte à embedder au format standardisé
    parts = []
    if _v("nom_produit"):
        parts.append(f"Nom Produit: {_v('nom_produit')}")
    if _v("nom_categorie"):
        parts.append(f"Catégorie: {_v('nom_categorie')}")
    if _v("description_produit"):
        parts.append(f"Description: {_v('description_produit')}")
    if _v("fournisseur"):
        parts.append(f"Fournisseur: {_v('fournisseur')}")

    # Ligne prix: valeur + devise + taxe + unité
    valeur = _v("valeur_prix")
    if valeur:
        prix_line = f"Prix: {valeur}"
        for extra in [_v("devise"), _v("taxe"), _v("unite")]:
            if extra:
                prix_line += f" {extra}"
        parts.append(prix_line)

    if _v("valeur_reponse_q1"):
        parts.append(f"Valeur réponse q1: {_v('valeur_reponse_q1')}")

    text_to_embed = "\n".join(parts)

    output_message = {
        "data": {
            "text": text_to_embed,
            **prix_data,
        },
        "collection": CollectionName.PRIX,
        "database":   database,
        "origin":     origin,
    }

    logger.info(
        f"📦 process_product_data_for_embedding: item prêt pour embedding "
        f"(source={source}, id_categorie={id_categorie}, "
        f"text_len={len(text_to_embed)})"
    )
    return output_message
