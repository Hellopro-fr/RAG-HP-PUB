import json
from common_utils.autres.CollectionName import CollectionName

def process_devis_data_for_embedding(devis_data: dict) -> dict:
    """
    Prend un dictionnaire de produit, le nettoie et prépare le message
    pour l’étape d’embedding.

    Retourne : Un dictionnaire prêt à être publié.
    """
    # Étape 1: Vérifier les données d'entrée
    if not isinstance(devis_data, dict):
        raise ValueError("Les données du devis doivent être un dictionnaire.")
    
    # Étape 4: Préparer le texte à embedder (À voir avec l'équipe en charge)
    text_to_embed = devis_data.get('text', '')
    
    # Étape 5: Ajouter les métadonnées nécessaires
    metadata = {
        key: value
        for key, value in devis_data.items() if key not in ['text']
    }
    
    # Étape 6: Construire le message de sortie
    output_message = {
        "data": {
            "text": text_to_embed,
            "metadata": metadata,
            # Todo: à remplacer ou à supprimer
            **{k: devis_data.get(k, "") for k in [
                "id_lead", "message", "message_hellopro", "categorie",
                "effectif", "prof_ou_part", "naf2", "naf5",
                "departement", "region", "pays", "critere", "societe",
                "date_ajout"
            ]}
        },
        "collection": CollectionName.DEVIS
    }
    
    # Afficher le message de sortie pour débogage
    print(f"🔍Devis-Processor: Message prêt pour l'embedding: {json.dumps(output_message, indent=2)}")
    
    # Étape 6: Retourner le message prêt à être publié
    print(f"📦 Devis-Processor: Produit '{devis_data.get('id_lead', 'ID inconnu')}' traité pour embedding.")
    return output_message