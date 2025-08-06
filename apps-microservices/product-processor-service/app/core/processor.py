# apps-microservices/product-processor-service/app/core/processor.py

import json
from common_utils.cleaning import clean_product_description

def process_product_data_for_embedding(product_data: dict) -> dict:
    """
    Prend un dictionnaire de produit, le nettoie et prépare le message
    pour l'étape d'embedding.
    
    Retourne: Un dictionnaire prêt à être publié.
    """
    # Étape 1: Nettoyer la description
    cleaned_desc = clean_product_description(product_data.get("description_produit", ""))

    # Étape 2: Préparer le texte à embedder
    text_to_embed = f"PRODUIT : {product_data.get('nom_produit', '')}. DESCRIPTION : {cleaned_desc}"

    # Étape 3: Construire le message de sortie
    output_message = {
        "metadata": {
            "id_produit": product_data.get("id_produit"),
            "nom_produit": product_data.get("nom_produit"),
            "description_nettoyee": cleaned_desc
        },
        "text_to_embed": text_to_embed,
        "target_collection": "products_collection"
    }
    
    return output_message