import json

from bs4 import BeautifulSoup

from common_utils.autres.CollectionName import CollectionName
from common_utils.cleaner.CleanHTML import CleanHTML
from common_utils.cleaner.AnonymizeText import AnonymizeText
from common_utils.ocr.DocumentTextExtractor import DocumentTextExtractor

def process_document_data_for_embedding(document_data: dict, bdd: str = "milvus") -> dict:
    
    # Étape 0: Initialisation du message de sortie
    output_message = {}
    
    # Étape 1: Vérifier les données d'entrée
    if not isinstance(document_data, dict):
        raise ValueError("Les données doivent être un dictionnaire.")

    # Étape 2.2: Extraire les textes dans le document 
    extractor = DocumentTextExtractor() 
    results   = extractor.process_single_file(document_data.get("document"))
    texts     = results['text']

    # Néttoyage
    cleaner      = CleanHTML(texts)
    cleaned_text = cleaner.clean()

    # Anonymisation
    anonymize = AnonymizeText()
    anonymized_text     = anonymize.anonymize_text(cleaned_text)
    text_to_embed_clean = anonymize.normalize_text(anonymized_text)


    # Étape 3: Construire le message de sortie
    output_message = {
        "data": {
            "text": text_to_embed_clean,
            **{k.replace("-", "_"): v for k, v in document_data.items() if k not in ['document']}
        },
        "collection": CollectionName.DOCUMENT,
        "database": bdd  
    }

    # Étape 4: Afficher le message de sortie pour débogage
    print(f"🔍Document-Echange-Processor: Message prêt: {json.dumps(output_message, indent=2)}")
    
    return output_message