import json
from common_utils.cleaner.CleanHTML import CleanHTML
from common_utils.autres.CollectionName import CollectionName

def process_product_data_for_embedding(product_data: dict) -> dict:
    """
    Prend un dictionnaire de produit, le nettoie et prépare le message
    pour l’étape d’embedding.

    Retourne : Un dictionnaire prêt à être publié.
    """
    # Étape 1: Vérifier les données d'entrée
    if not isinstance(product_data, dict):
        raise ValueError("Les données du produit doivent être un dictionnaire.")
    
    # Étape 2: Nettoyer la description du produit
    cleaner = CleanHTML(product_data.get("description", ""))
    cleaned_description = cleaner.clean()
    
    # Étape 3: Remplacer la description nettoyée dans les données du produit
    if cleaned_description is not None:
        product_data["description"] = cleaned_description
    
    # Étape 4: Préparer le texte à embedder (À voir avec l'équipe en charge)
    text_to_embed = (
        f"TITRE DU PRODUIT : {product_data.get('nom_produit', '')}\n"
        f"DESCRIPTION : {cleaned_description}\n"
        f"PRIX: {product_data.get('prix', '')}\n"
        f"CATEGORIE: {product_data.get('nom_categorie', '')}\n"
        f"LIVRAISON: {product_data.get('livraison', '')}\n"
        f"STOCK: {product_data.get('stock', '')}"
    )
    
    # Étape 5: Ajouter les métadonnées nécessaires
    metadata = {
        key: value
        for key, value in product_data.items()
    }
    
    # Étape 6: Construire le message de sortie
    output_message = {
        "data": {
            "embedding": text_to_embed,
            "metadata": metadata,
            **{k: product_data.get(k, "") for k in [
                "id_produit", "nom_produit", "id_categorie", "description",
                "nom_categorie", "id_fournisseur", "fournisseur", "domaine"
            ]}
        },
        "collection": CollectionName.PRODUIT
    }
    
    # Afficher le message de sortie pour débogage
    print(f"🔍 Product-Processor: Message prêt pour l'embedding: {json.dumps(output_message, indent=2)}")
    
    # Étape 6: Retourner le message prêt à être publié
    print(f"📦 Product-Processor: Produit '{product_data.get('id_produit', 'ID inconnu')}' traité pour embedding.")
    return output_message