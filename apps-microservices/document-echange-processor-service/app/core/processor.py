import json
import re
import logging
import os

from common_utils.autres.CollectionName import CollectionName
from common_utils.cleaner.CleanHTML import CleanHTML
from common_utils.cleaner.AnonymizeText import AnonymizeText
from common_utils.ocr.DocumentTextExtractor import DocumentTextExtractor
from common_utils.grpc_clients import llm_client

PROMPT_NETTOYAGE = """
**Rôles** :

1. **Expert en contenu B2B** : connaît les documents B2B (devis, catalogues, plaquettes, fiches techniques) et distingue le contenu métier/produit des mentions légales, CGV, disclaimers et informations marketing.
2. **Nettoyeur / Formateur JSON** : s’assure que le résultat est strictement en JSON avec la clé "contenu", sans ajouter ni supprimer d’autres informations que celles à exclure.

Instructions :

Voici le texte initial à nettoyer :
{content}

Tu es **Expert en contenu B2B** et **JSON Formatter**.
Ta tâche est de supprimer uniquement les informations suivantes :

1. **Mentions légales** : informations administratives ou légales de l’entreprise (RCS, SIRET, TVA, capital, forme juridique, adresse du siège).
2. **Conditions contractuelles** : clauses de contrats ou devis (CGV, CGA, CGU, réserve de propriété, conditions de paiement/livraison, mentions d’acceptation implicite).
3. **Mentions de non-responsabilité / disclaimers** : limitations de responsabilité ou avertissements (modifications sans préavis, photos non contractuelles, informations données à titre indicatif).
4. **Mentions réglementaires / légales spécifiques** : références à des lois, propriété intellectuelle, normes, certifications si elles apparaissent uniquement en footer ou bas de page.
5. **Mentions marketing institutionnelles** : slogans, accroches, messages de notoriété ou labels branding.
Ne pas ajouter ni supprimer d’autres informations.

Retourne le texte strictement dans ce format JSON :

```json
{{
  "contenu": "<texte nettoyé>"
}}
```

Si aucune information à exclure n’est présente, retourne le texte d’entrée exact dans le même format JSON.
"""

def extract_contenu(api_response: dict) -> str:
    """
    Extrait automatiquement la clé 'contenu' 
    depuis un champ 'response' contenant du JSON encodé en markdown.
    """
    if "response" not in api_response:
        raise KeyError("La clé 'response' est absente de la réponse API")

    texte = api_response["response"]

    # Nettoyer les balises markdown ```json ... ```
    json_str = re.sub(r"^```json\n|\n```$", "", texte.strip(), flags=re.MULTILINE)

    # Charger en dictionnaire Python
    try:
        json_data = json.loads(json_str)
    except json.JSONDecodeError as e:
        raise ValueError(f"Impossible de parser la réponse en JSON: {e}")

    # Retourner la valeur de 'contenu'
    return json_data.get("contenu", "")


async def process_document_data_for_templating(document_data: dict, bdd: str = "milvus") -> dict:
    
    # Étape 0: Initialisation du message de sortie
    output_message = {}
    
    # --- CONFIGURATION DU LOGGING PAR DOCUMENT ---
    document_path = document_data.get("document")
    if not document_path:
        raise ValueError("Le champ 'document' est manquant dans document_data")

    # Extraire le nom du fichier sans extension
    base_name = os.path.splitext(os.path.basename(document_path))[0]
    log_file = f"{base_name}.txt"

    # Configurer le logger
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(log_file, mode="w", encoding="utf-8"),
            logging.StreamHandler()  # affiche aussi dans la console
        ]
    )

    logging.info(f"--- Début du traitement pour le document : {document_path} ---")


    # Étape 1: Vérifier les données d'entrée
    if not isinstance(document_data, dict):
        raise ValueError("Les données doivent être un dictionnaire.")

    # Étape 2.2: Extraire les textes dans le document 
    extractor = DocumentTextExtractor() 
    results   = extractor.process_single_file(document_data.get("document"))
    texts     = results['text']
    method    = results['method']

    logging.info(f"\n\nMéthode utilisée : {method}")
    logging.info(f"\n\nTexte juste après extraction : {texts}")

    # Néttoyage
    cleaner      = CleanHTML(texts)
    cleaned_text = cleaner.clean()

    logging.info(f"\n\nTexte juste après nettoyage : {cleaned_text}")

    # Anonymisation
    anonymize = AnonymizeText()
    anonymized_text     = anonymize.anonymize_text(cleaned_text)
    text_to_embed_clean = anonymize.normalize_text(anonymized_text)

    logging.info(f"\n\nTexte juste après Anonymisation : {text_to_embed_clean}")


    # Suppression des info inutiles via llm
    payload = {
        "prompt" : json.dumps(PROMPT_NETTOYAGE.format(content=text_to_embed_clean)),
        "max_tokens" : 32700,
        "temperature": 0.7
    }

    try: 
        response = await llm_client.get_llm_chat_response(payload)
        text_to_embed_clean = extract_contenu(response.json())
    except:
        pass

    # Étape 3: Construire le message de sortie
    output_message = {
        "data": {
            "text": text_to_embed_clean,
            **{k.replace("-", "_"): v for k, v in document_data.items() if k not in ['document']}
        },
        "collection": CollectionName.DOCUMENT,
        "database": bdd,
        "log_file": log_file  
    }

    logging.info(f"\n\nTexte juste après nettoyage bruit via LLM : {text_to_embed_clean}")
    # Étape 4: Afficher le message de sortie pour débogage
    print(f"🔍Document-Echange-Processor: Message prêt: {json.dumps(output_message, indent=2)}")
    
    return output_message