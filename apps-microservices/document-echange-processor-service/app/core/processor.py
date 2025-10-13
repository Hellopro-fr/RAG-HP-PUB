import json
import re
import logging
import os

from common_utils.autres.CollectionName import CollectionName
from common_utils.cleaner.CleanHTML import CleanHTML
from common_utils.cleaner.AnonymizeText import AnonymizeText
from common_utils.ocr.DocumentTextExtractor import DocumentTextExtractor
from common_utils.grpc_clients import llm_client
from common_utils.grpc_clients.schemas.chat import ChatRequest


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
json
{{ "contenu": "<texte nettoyé>" }}
Si aucune information à exclure n’est présente, retourne le texte d’entrée exact dans le même format JSON.
"""

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

    # Créer un logger spécifique pour ce document (pas le logger root)
    logger = logging.getLogger(f"doc_processor_{base_name}")
    logger.setLevel(logging.INFO)
    
    # Supprimer les handlers existants pour ce logger
    logger.handlers.clear()
    
    # Ajouter les nouveaux handlers
    file_handler = logging.FileHandler(log_file, mode="w", encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    # Empêcher la propagation au logger root
    logger.propagate = False

    logger.info(f"--- Début du traitement pour le document : {document_path} ---")

    try:
        # Étape 1: Vérifier les données d'entrée
        if not isinstance(document_data, dict):
            raise ValueError("Les données doivent être un dictionnaire.")

        # Étape 2.2: Extraire les textes dans le document 
        extractor = DocumentTextExtractor() 
        results   = extractor.process_single_file(document_data.get("document"))
        texts     = results['text']
        method    = results['method']

        logger.info(f"\n\nMéthode utilisée : {method}")
        logger.info(f"\n\nTexte juste après extraction : {texts}")

        # Néttoyage
        cleaner      = CleanHTML(texts)
        cleaned_text = cleaner.clean()

        # Anonymisation
        anonymize = AnonymizeText()
        anonymized_text     = anonymize.anonymize_text(cleaned_text)
        text_to_embed_clean = anonymize.normalize_text(anonymized_text)

        logger.info(f"\n\nTexte juste après anonymisation : {text_to_embed_clean}")

        # Suppression des info inutiles via llm
        try:
            chat_request = ChatRequest(
                prompt=json.dumps(PROMPT_NETTOYAGE.format(content=text_to_embed_clean)),
                max_tokens=30000,
                temperature=0.7,
                enable_thinking=False
            )

            raw_text = await llm_client.get_llm_chat_response(chat_request)

            # Parsing de la réponse
            match = re.search(r'\{.*\}', raw_text, re.DOTALL)
            if match:
                json_string = match.group(0)
                parsed_json = json.loads(json_string)
                contenu = parsed_json.get("contenu")
                if not contenu:
                    raise ValueError(f"Le champ 'contenu' est manquant ou vide dans la réponse JSON: {raw_text}")
                else:
                    text_to_embed_clean = contenu
            else:
                raise ValueError(f"Aucun bloc JSON trouvé dans la sortie du LLM: {raw_text}")

            # Extraction du texte nettoyé

        except Exception as e:
            logger.warning(f"Erreur lors du nettoyage LLM : {type(e).__name__} - {e}")

        # Étape 3: Construire le message de sortie
        output_message = {
            "data": {
                "text": text_to_embed_clean,
                **{k.replace("-", "_"): v for k, v in document_data.items() if k not in ['document']}
            },
            "collection": CollectionName.DOCUMENT,
            "database": bdd,
            "log_file": log_file,
            "base_name": base_name
        }

        logger.info(f"\n\nTexte juste après nettoyage bruit via LLM : {text_to_embed_clean}")
        
        # Étape 4: Afficher le message de sortie pour débogage
        print(f"🔍Document-Echange-Processor: Message prêt: {json.dumps(output_message, indent=2)}")
        
        return output_message
    
    finally:
        # Nettoyer les handlers pour libérer le fichier
        for handler in logger.handlers[:]:
            handler.close()
            logger.removeHandler(handler)