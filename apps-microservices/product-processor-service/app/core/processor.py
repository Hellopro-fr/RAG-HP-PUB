import json
import logging
from common_utils.cleaner.CleanHTML import CleanHTML
from common_utils.autres.CollectionName import CollectionName

logger = logging.getLogger(__name__)

def process_product_data_for_embedding(product_data: dict,bdd: str = "qdrant",origin: str = "bo", mode: str = "default") -> dict:
    """
    Prend un dictionnaire de produit, le nettoie et prépare le message
    pour l’étape d’embedding.

    Retourne : Un dictionnaire prêt à être publié.
    """
    # Étape 1: Vérifier les données d'entrée
    if not isinstance(product_data, dict):
        raise ValueError("Les données du produit doivent être un dictionnaire.")
    
    # Étape 2: Nettoyer la description du produit
    cleaner = CleanHTML(product_data.get("text", ""))
    cleaned_text = cleaner.clean()
    
    
    # Étape 4: Préparer le texte à embedder (À voir avec l'équipe en charge)
    text_to_embed = cleaned_text
    
    # Étape 5: Construire le message de sortie
    output_message = {
        "data": {
            "text": text_to_embed,
            **{k: v for k, v in product_data.items() if k not in ['text', 'domaine_dspi']}
        },
        "collection": CollectionName.PRODUIT,
        "database": bdd,
        "origin": origin,
        "mode": mode
    }
    
    # Afficher le message de sortie pour débogage
    logger.debug(f"🔍 Product-Processor: Message prêt pour l'embedding: {json.dumps(output_message, indent=2)}")
    
    # Étape 6: Retourner le message prêt à être publié
    logger.info(f"📦 Product-Processor: Produit '{product_data.get('id_produit', 'ID inconnu')}' traité pour embedding.")
    return output_message