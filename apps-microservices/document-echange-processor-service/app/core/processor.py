import json
import re
import logging
import os
from concurrent.futures import ProcessPoolExecutor , ThreadPoolExecutor

from common_utils.autres.CollectionName import CollectionName
from common_utils.cleaner.CleanHTML import CleanHTML
from common_utils.cleaner.AnonymizeText import AnonymizeText
from common_utils.ocr.DeepseekOCRDocExtractor import DeepseekOCRDocExtractor
from common_utils.grpc_clients import llm_client
from common_utils.grpc_clients.schemas.chat import ChatRequest
from vllm.transformers_utils.tokenizer import get_tokenizer
from common_utils.database.MilvusDocumentCrud import MilvusDocumentCrud


# TOKENIZER = get_tokenizer("deepseek-ai/DeepSeek-R1", trust_remote_code=True)
# MAX_MODEL_LEN = 128000 # Correspond à la limite théorique du modèle DeepSeek-R1
# # On définit une limite de sécurité un peu en dessous du max pour éviter les erreurs "off-by-one"
# SAFE_MAX_LEN = MAX_MODEL_LEN - 512

MAX_OUTPUT_TOKEN = 64000

PROMPT_NETTOYAGE = """
Tu es un expert en analyse de documents B2B (devis, catalogues, fiches techniques, plaquettes commerciales,savoir-faire, autre type).
**Tâche**:
Nettoyer le texte en supprimant **uniquement et exactement** les 5 catégories d'informations listées ci-dessous. Ne modifie, n'ajoute ni ne supprime aucune autre information.
**Texte à analyser** : 
{content}
**Informations à supprimer** :
1. **Mentions légales administratives** : RCS, SIRET, SIREN, TVA intracommunautaire, capital social, forme juridique, adresse du siège social
2. **Clauses contractuelles** : CGV, CGA, CGU, conditions de paiement, conditions de livraison, réserve de propriété, clauses d'acceptation
3. **Disclaimers** : limitations de responsabilité, mentions "sous réserve de modifications", "photos non contractuelles", "informations à titre indicatif"
4. **Mentions réglementaires isolées** : références légales, propriété intellectuelle, normes ou certifications situées uniquement en footer/bas de page
5. **Slogans marketing institutionnels** : accroches génériques, messages de notoriété, labels de marque sans lien direct avec le produit/service
**Règles strictes** :
- Conserve tout le contenu métier : descriptions produits, caractéristiques techniques, prix, références, données opérationnelles
- Si tu supprimes du texte, préserve la cohérence et la lisibilité du contenu restant
- Ne reformule rien, ne corrige aucune faute, ne réorganise pas le texte
**Format de sortie obligatoire** :
Si des informations ont été supprimées  → retourne uniquement:
json
{{ "contenu": "texte nettoyé ici" }}
Si aucune information à supprimer n'est détectée  → retourne:
json
{{ "contenu": "ok" }}
"""

def make_chat_request(prompt_template, content,temperature=0.7):
    """
    Crée une requête chat en ajustant automatiquement les tokens de sortie
    selon la taille du prompt.

    Args:
        prompt_template (str): template du prompt avec placeholder {content}
        content (str): texte à insérer dans le prompt

    Returns:
        ChatRequest prêt à être envoyé au modèle
    """
    
    # Construire le texte complet du prompt
    prompt_text = prompt_template.format(content=content)
    prompt_json = json.dumps(prompt_text)
    
    # # Compter les tokens du prompt
    # input_tokens = len(TOKENIZER.encode(prompt_json))
    
    # # Calculer le nombre maximum de tokens possibles pour la sortie
    # remaining_tokens = SAFE_MAX_LEN - input_tokens
    
    # # Sécurité : éviter les valeurs négatives ou trop hautes
    # max_output_tokens = max(0,remaining_tokens)
    
    # # Message d’avertissement utile pour le débogage
    # print(f"[INFO] Prompt = {input_tokens} tokens | Output = {max_output_tokens} tokens disponibles.")
    
    # # Construire la requête
    chat_request = ChatRequest(
        prompt=prompt_json,
        max_tokens=MAX_OUTPUT_TOKEN,
        temperature=temperature,
        enable_thinking=True
    )
    
    return chat_request

async def process_document_data_for_templating(document_data: dict, bdd: str = "milvus" , executor: ProcessPoolExecutor | ThreadPoolExecutor = None) -> dict:
    
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

        res = await MilvusDocumentCrud().get_document(fichier_source=document_data.get("fichier_source"))

        tab_data = res.get('data',[])

        if tab_data:
            text_bdd = tab_data[0].get('text','').strip()
            if text_bdd:
                logger.info("PJ déjà traité")
                return None
            

        # Étape 1: Vérifier les données d'entrée
        if not isinstance(document_data, dict):
            raise ValueError("Les données doivent être un dictionnaire.")


        extractor = DeepseekOCRDocExtractor()
        results = await extractor.extract_from_url(document_data.get("document"))
        
        texts     = results['text']
        text_to_embed_clean = ""
        # logger.info(f"\n\nTexte juste après extraction : {texts}")

        # Néttoyage
        #Suppression des balises img | watermark + ses contenus
        if texts:  
            pattern = re.compile(r"<(img|watermark)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
            texts = re.sub(pattern, "", texts)

            cleaner      = CleanHTML(texts)
            cleaned_text = cleaner.clean()

            # Anonymisation
            anonymize = AnonymizeText()
            anonymized_text     = anonymize.anonymize_text(cleaned_text)
            text_to_embed_clean = anonymize.normalize_text(anonymized_text)

            # Suppression des info inutiles via llm
            try:

                chat_request = make_chat_request(PROMPT_NETTOYAGE,text_to_embed_clean)
                raw_response_dict = await llm_client.get_llm_chat_response(chat_request)
        
                # Construction du payload de métriques
                response_details = raw_response_dict.get('response', {})
                usage_details = response_details.get('usage', {})
                error_details = response_details.get('error', {})
                state_llm = 1 if not error_details else 2

                metric_payload = {
                    "source_service": "document-echange-processor-service",
                    "url": document_path,
                    "state_llm": state_llm,
                    "prompt_tokens": usage_details.get('prompt_tokens'),
                    "completion_tokens": usage_details.get('completion_tokens'),
                    "total_tokens": usage_details.get('total_tokens'),
                    "model": response_details.get('model'),
                    "raw_response_on_error": raw_response_dict if state_llm == 2 else None,
                    "process_id": 33
                }
                
                if state_llm == 2:
                    raise ValueError(f"Erreur du LLM: {raw_response_dict}")

                # Parsing de la réponse
                raw_text = raw_response_dict.get('full_message', '')

                # Parsing de la réponse
                match = re.search(r'\{.*\}', raw_text, re.DOTALL)
                if match:
                    json_string = match.group(0)
                    parsed_json = json.loads(json_string)
                    contenu = parsed_json.get("contenu")
                    if not contenu:
                        raise ValueError(f"Le champ 'contenu' est manquant ou vide dans la réponse JSON: {raw_text}")
                    elif contenu != "ok":
                        text_to_embed_clean = contenu
                        logger.info(f"\n\nTexte juste après nettoyage : {text_to_embed_clean}")
                else:
                    raise ValueError(f"Aucun bloc JSON trouvé dans la sortie du LLM: {raw_text}")

            except Exception as e:
                logger.warning(f"Erreur lors du nettoyage LLM : {type(e).__name__} - {e}")
                error_str = f"Erreur lors du nettoyage LLM. Erreur: {e}"
                # S'assurer qu'on a un payload de métrique même en cas d'erreur
                if not metric_payload:
                    metric_payload = {
                        "source_service": "template-llm-service",
                        "url": document_path,
                        "state_llm": 2, # Erreur
                        "error_message": error_str
                    }
                return {
                    "status": "error",
                    "original_message": document_data,
                    "error_message": error_str,
                    "metric_payload": metric_payload
                }

        # Étape 3: Construire le message de sortie
        output_message = {
            "data": {
                "text": text_to_embed_clean,
                "embedding" : [0.0]*1024,
                "fichier_source" : document_data.get("fichier_source","inconnu"),
                "id_demande" : document_data.get("id_demande","inconnu"),
                "id_fournisseur" : document_data.get("id_fournisseur","inconnu"),
                # **{k.replace("-", "_"): v for k, v in document_data.items() if k in ['fichier_source']}
            },
            "collection": CollectionName.DOCUMENT,
            "database": bdd,
            "log_file": log_file,
            "base_name": base_name
        }

        # logger.info(f"\n\nTexte juste après nettoyage bruit via LLM : {text_to_embed_clean}")
        
        # Étape 4: Afficher le message de sortie pour débogage
        # print(f"🔍Document-Echange-Processor: Message prêt: {json.dumps(output_message, indent=2)}")
        print(f"🔍Document-Echange-Processor: Message prêt")
        
        return {
                "status": "success",
                "processed_message": output_message,
                "metric_payload": metric_payload
            }
    
    finally:
        # Nettoyer les handlers pour libérer le fichier
        for handler in logger.handlers[:]:
            handler.close()
            logger.removeHandler(handler)