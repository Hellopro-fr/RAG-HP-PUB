import json
from datetime import datetime, timezone
from common_utils.autres.CollectionName import CollectionName

def convertir_date_to_timestamp(date_str: str) -> int:
    """
    date_str = "2023-10-23T13:18:05Z"
    Convertit une date en timestamp (int).
    """

    # Conversion en datetime (timezone UTC)
    dt = datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)

    # Conversion en timestamp (secondes)
    timestamp = int(dt.timestamp())

    return timestamp

def convert_fields_to_int(data: dict, fields: list[str]) -> dict:
    """
    Convertit certains champs en int si possible.
    """
    for field in fields:
        if field in data:
            try:
                data[field] = int(data[field])
            except (ValueError, TypeError):
                pass 
    return data

def process_devis_data_for_embedding(devis_data: dict, bdd: str = "qdrant") -> dict:
    if not isinstance(devis_data, dict):
        raise ValueError("Les données du devis doivent être un dictionnaire.")
    
    text_to_embed = devis_data.get('text', '')
    devis_clean = {k.replace("-", "_"): v for k, v in devis_data.items() if k not in ['text']}
    
    # ✅ Conversion en int centralisée
    FIELDS_TO_INT = ["lead_id", "id_produit", "id_categorie"]
    devis_clean = convert_fields_to_int(devis_clean, FIELDS_TO_INT)
    
    # ✅ Transformation liste_frns en tableau
    if "liste_frns" in devis_clean and isinstance(devis_clean["liste_frns"], str):
        devis_clean["liste_frns"] = [frn.strip() for frn in devis_clean["liste_frns"].split(",") if frn.strip()]

    # ✅ Conversion date_du_lead en timestamp
    if "date_du_lead" in devis_clean and isinstance(devis_clean["date_du_lead"], str):
        try:
            devis_clean["date_du_lead"] = convertir_date_to_timestamp(devis_clean["date_du_lead"])
        except ValueError:
            pass
    
    output_message = {
        "data": {
            "text": text_to_embed,
            **devis_clean
        },
        "collection": CollectionName.DEVIS,
        "database": bdd
    }
    
    print(f"🔍Devis-Processor: Message prêt pour l'embedding: {json.dumps(output_message, indent=2, ensure_ascii=False)}")
    print(f"📦 Devis-Processor: Lead '{devis_clean.get('lead_id', 'ID inconnu')}' traité pour embedding.")
    
    return output_message
