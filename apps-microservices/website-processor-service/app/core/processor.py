import json
from common_utils.autres.CollectionName import CollectionName
from common_utils.cleaner.TrafilaturaCleaning import TrafilaturaHp

def process_website_data_for_embedding(website_data: dict) -> dict:
    """
    Prend un dictionnaire de produit, le nettoie et prépare le message
    pour l’étape d’embedding.

    Retourne : Un dictionnaire prêt à être publié.
    """
    # Étape 1: Vérifier les données d'entrée
    if not isinstance(website_data, dict):
        raise ValueError("Les données doivent être un dictionnaire.")
    
    # Étape 2: Préparer le texte à embedder (À voir avec l'équipe en charge)
    text_to_embed = website_data.get('text', '')

    # Etape 3: Nettoyer les données  
    trafila = TrafilaturaHp()
    trafila.info = text_to_embed
    text_to_embed_clean = trafila.extract()
    
    
    # Étape 5: Construire le message de sortie
    output_message = {
        "data": {
            "text": text_to_embed_clean,
            # Todo: à modifier si nécessaire
            **{k: v for k, v in website_data.items() if k not in ['text']}
        },
        "collection": CollectionName.SITEWEB
    }    

    # Afficher le message de sortie pour débogage
    print(f"🔍Website-Processor: Message prêt pour l'embedding: {json.dumps(output_message, indent=2)}")
    
    # Étape 6: Retourner le message prêt à être publié
    print(f"📦 Website-Processor: Website traité pour embedding.")
    return output_message