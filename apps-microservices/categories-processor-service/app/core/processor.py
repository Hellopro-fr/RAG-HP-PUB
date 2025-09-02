import json
from common_utils.cleaner.CleanHTML import CleanHTML
from common_utils.autres.CollectionName import CollectionName

def process_categories_data_for_embedding(categories_data: dict,bdd: str = "qdrant") -> dict:
    """
    Prend un dictionnaire de catégories, le nettoie et prépare le message
    pour l’étape d’embedding.

    Retourne : Un dictionnaire prêt à être publié.
    """
    # Étape 1: Vérifier les données d'entrée
    if not isinstance(categories_data, dict):
        raise ValueError("Les données des catégories doivent être un dictionnaire.")
    
    # Étape 2: Nettoyer le texte à embedder
    cleaner = CleanHTML(categories_data.get("text", ""))
    cleaned_text = cleaner.clean()    
    
    # Étape 4: Préparer le texte à embedder
    text_to_embed = cleaned_text
    
    # Étape 5: Ajouter les métadonnées nécessaires
    metadata = {
        key: value
        for key, value in categories_data.items() if key not in ['text']
    }
    
    # Étape 6: Construire le message de sortie
    output_message = {
        "data": {
            "text": text_to_embed,
            **{k: v for k, v in categories_data.items() if k not in ['text']}

        },
        "collection": CollectionName.CATEGORIE,
        "database": bdd
    }
    
    # Afficher le message de sortie pour débogage
    print(f"🔍Cateogries-Processor: Message prêt pour l'embedding: {json.dumps(output_message, indent=2)}")
    
    # Étape 6: Retourner le message prêt à être publié
    print(f"📦 🔍Cateogries-Processor: catégories '{categories_data.get('id_categorie', 'ID inconnu')}' traité pour embedding.")
    return output_message