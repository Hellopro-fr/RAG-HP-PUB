import json
from common_utils.autres.CollectionName import CollectionName
from common_utils.cleaner.TrafilaturaCleaning import TrafilaturaHp

def process_website_data_for_embedding(website_data: dict, bdd: str = "qdrant") -> dict:
    """
    Prend un dictionnaire de produit, le nettoie et prépare le message
    pour l’étape d’embedding.

    Retourne : Un dictionnaire prêt à être publié.
    """
    # Étape 1: Vérifier les données d'entrée
    if not isinstance(website_data, dict):
        raise ValueError("Les données doivent être un dictionnaire.")
    
    # Étape 2: Préparer le texte à embedder (À voir avec l'équipe en charge)

    info = {
            "url": website_data.get("url",""),
            "content": website_data.get("text",""),
            "fetch": False
        }

    # Etape 3: Nettoyer les données  
    trafila = TrafilaturaHp(info)
    res_clean = trafila.extract(info)
    text_to_embed_clean = res_clean.content
    
    # Étape 5: Construire le message de sortie
    output_message = {
        "data": {
            "text": text_to_embed_clean,
            # Todo: à modifier si nécessaire
            **{k: v for k, v in website_data.items() if k not in ['text']}
        },
        "collection": CollectionName.SITEWEB,
        "database": bdd  
    }    

    # Afficher le message de sortie pour débogage
    print(f"🔍Website-Processor: Message prêt pour l'embedding: {json.dumps(output_message, indent=2)}")
    
    # Étape 6: Retourner le message prêt à être publié
    print(f"📦 Website-Processor: Website traité pour embedding.")
    return output_message