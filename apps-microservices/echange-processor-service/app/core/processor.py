import json
import logging
from common_utils.autres.CollectionName import CollectionName

logger = logging.getLogger(__name__)

def process_echange_data_for_embedding(echange_data: dict, bdd: str) -> dict:
    """
    Prend un dictionnaire de produit, le nettoie et prépare le message
    pour l’étape d’embedding.

    Retourne : Un dictionnaire prêt à être publié.
    """
    # Étape 1: Vérifier les données d'entrée
    if not isinstance(echange_data, dict):
        raise ValueError("Les données doivent être un dictionnaire.")
    
    # Étape 4: Préparer le texte à embedder (À voir avec l'équipe en charge)
    text_to_embed = echange_data.get('text', '')
    conversation_id = f"{echange_data.get('id_demande', 'unknown')}_{echange_data.get('id_fournisseur', 'unknown')}"
    
    
    # Étape 6: Construire le message de sortie
    output_message = {
        "data": {
            "text": text_to_embed,
            "conversation_id": conversation_id,
             **{k.replace("-", "_"): v for k, v in echange_data.items() if k not in ['text','conversation_id']}
        },
        "collection": CollectionName.ECHANGE,
        "database": bdd
    }
                

    # Afficher le message de sortie pour débogage
    logger.debug(f"🔍 Echange-Processor: Message prêt pour l'embedding: {json.dumps(output_message, indent=2)}")
    
    # Étape 6: Retourner le message prêt à être publié
    logger.info(f"📦 Echange-Processor: Echange traité pour embedding.")
    return output_message