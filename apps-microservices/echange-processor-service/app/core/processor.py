import json
from common_utils.cleaner.CleanHTML import CleanHTML
from common_utils.autres.CollectionName import CollectionName

def process_echange_data_for_embedding(echange_data: dict) -> dict:
    """
    Prend un dictionnaire d'échange, le nettoie et prépare le message
    pour l’étape d’embedding.

    Retourne : Un dictionnaire prêt à être publié.
    """
    # Étape 1: Vérifier les données d'entrée
    if not isinstance(echange_data, dict):
        raise ValueError("Les données de l'échange doivent être un dictionnaire.")
    
    # Étape 2: Nettoyer le texte de l'échange
    cleaner = CleanHTML(echange_data.get("text", ""))
    cleaned_text = cleaner.clean()
    
    # Étape 3: Remplacer le texte nettoyée dans les données de l'échange
    if cleaned_text is not None:
        echange_data["text"] = cleaned_text
    
    # Étape 4: Préparer le texte à embedder (À voir avec l'équipe en charge)
    text_to_embed = (
        f"ECHANGE : {echange_data.get('text', '')}"
    )
    
    # Étape 5: Ajouter les métadonnées nécessaires
    metadata = {
        key: value
        for key, value in echange_data.items()
    }
    
    # Étape 6: Construire le message de sortie
    output_message = {
        "data": {
            "embedding": text_to_embed,
            "metadata": metadata,
            **{k: echange_data.get(k, "") for k in echange_data.items()}
        },
        "collection": CollectionName.ECHANGE
    }
    
    # Afficher le message de sortie pour débogage
    print(f"🔍 Echange-Processor: Message prêt pour l'embedding: {json.dumps(output_message, indent=2)}")
    
    # Étape 6: Retourner le message prêt à être publié
    id_echange = f"{echange_data.get('id_demande', "ID DEMANDE INCONNU")} - {echange_data.get('id_fournisseur', "ID FOURNISSEUR INCONNU")}"
    print(f"📦 Echange-Processor: Échange '{id_echange}' traité pour embedding.")
    return output_message