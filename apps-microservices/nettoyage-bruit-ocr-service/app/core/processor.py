
import re
import json
import asyncio
import logging
from typing import List, Dict

from common_utils.autres.CollectionName import CollectionName
from common_utils.grpc_clients import llm_client
from common_utils.grpc_clients.schemas.chat import ChatRequest
# from common_utils.metrics.prometheus import measure_processing_time


MAX_OUTPUT_TOKEN = 64000

PROMPT_NETTOYAGE = """
Tu es un expert en analyse de documents B2B (devis, catalogues, fiches techniques, plaquettes commerciales,savoir-faire, autre type).
**Tâche**:
Si le texte est en français, nettoye-le en supprimant **uniquement et exactement** les 5 catégories d'informations listées ci-dessous. Ne modifie, n'ajoute ni ne supprime aucune autre information.
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
Si le contenu fourni n'est pas en français (en anglais, en allemand , en espagnol, etc)  → retourne:
json
{{ "contenu": "" }}
Si aucune information à supprimer n'est détectée ou le contenu fourni est en anglais  → retourne:
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
    
    # # Construire la requête
    chat_request = ChatRequest(
        prompt=prompt_json,
        max_tokens=MAX_OUTPUT_TOKEN - 512,
        temperature=temperature,
        enable_thinking=True
    )
    
    return chat_request

async def _process_single_message(document_item: dict) -> dict:
    output_message = {}

    nb_pages = document_item.get("nb_pages","")
    document_data = document_item.get("data",{})
    text_to_embed_clean = document_data.get("text","")
    cleaned_text = text_to_embed_clean
    
    metric_payload = {}

    try:

        chat_request = make_chat_request(PROMPT_NETTOYAGE,text_to_embed_clean)
        raw_response_dict = await llm_client.get_llm_chat_response(chat_request)

        # Construction du payload de métriques
        response_details = raw_response_dict.get('response', {})
        usage_details = response_details.get('usage', {})
        error_details = response_details.get('error', {})
        state_llm = 1 if not error_details else 2

        doc_url = document_data.get("fichier_source").replace(r"\/", "/")
        metric_payload = {
            "source_service": "nettoyage-bruit-ocr-service",
            "url": f"{doc_url}({nb_pages} page(s))",
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
                cleaned_text = contenu
        else:
            # raise ValueError(f"Aucun bloc JSON trouvé dans la sortie du LLM")
            return {
                "status": "error",
                "original_message": document_item,
                "error_message": "Aucun bloc JSON trouvé dans la sortie du LLM",
                "metric_payload": metric_payload
            }

    except Exception as e:
        logging.warning(f"Erreur lors du nettoyage LLM : {type(e).__name__} - {e}")
        error_str = f"Erreur lors du nettoyage LLM. Erreur: {e}"
        # S'assurer qu'on a un payload de métrique même en cas d'erreur
        if not metric_payload:
            metric_payload = {
                "source_service": "nettoyage-bruit-ocr-service",
                "url": document_data.get('document'),
                "state_llm": 2, # Erreur
                "error_message": error_str
            }
        return {
            "status": "error",
            "original_message": document_item,
            "error_message": error_str,
            "metric_payload": metric_payload
        }

    output_message = {
        "data": {
            "text": cleaned_text,
            **{k: v for k, v in document_data.items() if k not in ["text"]}
        },
        "collection": CollectionName.DOCUMENT,
        "database": "milvus",
        "nb_pages": nb_pages
    }

    return {
            "status": "success",
            "processed_message": output_message,
            "metric_payload": metric_payload
        }

# @measure_processing_time(service_name="nettoyage-bruit-ocr-service", payload_arg_name="messages")
async def nettoyer_bruits_ocr(documents: List[Dict]) -> List[Dict]:    
    if not documents:
        return []

    # --- Étape 1: Créer une tâche asyncio pour chaque message ---
    tasks = [_process_single_message(msg) for msg in documents]
    
    # --- Étape 2: Exécuter toutes les tâches en parallèle ---
    processed_results = await asyncio.gather(*tasks)
        
    # --- Étape 3: Journalisation des résultats ---
    print(f"   -> Nettoyage des bruits OCR en batch terminée pour {len(processed_results)} messages.")
    for res in processed_results:
        msg = res.get('processed_message') or res.get('original_message')
        url = msg['data'].get('fichier_source', 'N/A')
        
        if res['status'] == 'success':
            page_type = msg['data'].get('page_type', 'N/A')
            content_len = msg.get('_diag_content_length', 'N/A')
            metric = res.get('metric_payload', {})
            model = metric.get('model', 'N/A')
            prompt_tokens = metric.get('prompt_tokens', 'N/A')
            completion_tokens = metric.get('completion_tokens', 'N/A')
            print(f"      • [SUCCESS] URL: {url} => Type: {page_type} [Model: {model}, PromptTokens: {prompt_tokens}, CompletionTokens: {completion_tokens}, ContentLen: {content_len}]")
        else:
            print(f"      • [FAILURE] URL: {url} => Erreur: {res.get('error_message', 'Inconnue')}")
            
    return processed_results
    