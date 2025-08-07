# apps-microservices/product-processor-service/app/core/processor.py

import json
from common_utils.cleaner.CleanHTML import CleanHTML

def process_product_data_for_embedding(product_data: dict) -> dict:
    """
    Prend un dictionnaire de produit, le nettoie et prépare le message
    pour l'étape d'embedding.
    
    Retourne: Un dictionnaire prêt à être publié.
    """
    # Étape 1: Vérifier les données d'entrée
    if not isinstance(product_data, dict):
        raise ValueError("Les données du produit doivent être un dictionnaire.")
    
    # Étape 2: Nettoyer la description du produit
    cleaner = CleanHTML(product_data.get("description_produit", ""))
    cleaned_description = cleaner.clean()
    
    # Étape 3: Remplacer la description nettoyée dans les données du produit
    product_data["description_produit"] = cleaned_description
    
    # Étape 4: Préparer le texte à embedder (À voir avec l'équipe en charge)
    text_to_embed = f"PRODUIT : {product_data.get('nom_produit', '')}. DESCRIPTION : {cleaned_description}"
    
    # Étape 5: Construire le message de sortie
    output_message = {
        "metadata": product_data,
        "embedding": text_to_embed,
        "target_collection": "products_collection"
    }
    
    # Afficher le message de sortie pour débogage
    print(f"🔍 Product-Processor: Message prêt pour l'embedding: {json.dumps(output_message, indent=2)}")
    
    # Étape 6: Retourner le message prêt à être publié
    print(f"📦 Product-Processor: Produit '{product_data.get('id_produit', 'ID inconnu')}' traité pour embedding.")
    return output_message