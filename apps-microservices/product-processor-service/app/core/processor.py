# apps-microservices/product-processor-service/app/core/processor.py

import json
from common_utils.cleaning import clean_product_description

def process_product_data_for_embedding(product_data: dict) -> dict:
    """
    Prend un dictionnaire de produit, le nettoie et prépare le message
    pour l’étape d’embedding.

    Retourne : Un dictionnaire prêt à être publié.
    """
    # Étape 1 : Nettoyer la description
    cleaned_desc = clean_product_description(product_data.get("description", ""))

    # Étape 2 : Préparer le texte à embedder
    text_to_embed = (
        f"TITRE DU PRODUIT : {product_data.get('nom_produit', '')}\n"
        f"DESCRIPTION : {cleaned_desc}\n"
        f"PRIX: {product_data.get('prix', '')}\n"
        f"CATEGORIE: {product_data.get('nom_categorie', '')}\n"
        f"LIVRAISON: {product_data.get('livraison', '')}\n"
        f"STOCK: {product_data.get('stock', '')}"
    )

    # Étape 3 : Construire les métadonnées automatiquement
    metadata = {
        key: value
        for key, value in product_data.items()
        if key not in ("description", "embedding")
    }
    metadata["description"] = cleaned_desc

    # Étape 4 : Retour final
    return {
        "collection": "produits",
        "data": {
            "embedding": text_to_embed,
            "description": cleaned_desc,
            **{k: product_data.get(k, "") for k in [
                "id_produit", "nom_produit", "id_categorie",
                "nom_categorie", "id_fournisseur", "fournisseur", "domaine"
            ]},
            "metadata": metadata
        }
    }
