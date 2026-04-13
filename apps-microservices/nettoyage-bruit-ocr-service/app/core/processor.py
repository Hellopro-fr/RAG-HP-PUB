
import re
import json
import asyncio
import logging
from typing import List, Dict
from concurrent.futures import ThreadPoolExecutor


from common_utils.autres.CollectionName import CollectionName
from common_utils.grpc_clients import llm_client
from common_utils.grpc_clients.schemas.chat import ChatRequest

logger = logging.getLogger(__name__)

_thread_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="llm_worker")

MAX_OUTPUT_TOKEN = 64000
MAX_CONTENT_CHARS = 60000

PROMPT_NETTOYAGE = """
Tu es un expert en analyse de documents B2B multilingues (devis, catalogues, fiches techniques, plaquettes commerciales,savoir-faire, autre type) et à l'aise en détection des langues utilisées dans un contenu spécifique.
**Texte à analyser** : 
{content}

**Tâche**:
Si la plupart du contenu fourni est en français , nettoie-le en supprimant **uniquement et exactement** les 5 catégories d'informations listées ci-dessous. Ne modifie, n'ajoute ni ne supprime aucune autre information.
Par contre , si la plupart du contenu fourni n'est pas en français , retourne uniquement:
json
{{ "contenu": "" }}

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
    
    if len(content) > MAX_CONTENT_CHARS:
        logger.warning("Content truncated: %d chars > %d max", len(content), MAX_CONTENT_CHARS)
        content = content[:MAX_CONTENT_CHARS]

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


def _run_async_in_thread(coro):
    """
    Exécute une coroutine async dans un thread séparé avec son propre event loop.
    """
    # Créer un nouveau event loop pour ce thread
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()

async def _process_single_message(document_item: dict) -> dict:
    """Votre fonction ASYNC existante - AUCUN CHANGEMENT."""
    output_message = {}

    nb_pages = document_item.get("nb_pages","")
    document_data = document_item.get("data",{})
    text_to_embed_clean = document_data.get("text","")
    cleaned_text = text_to_embed_clean
    
    metric_payload = {}

    try:
        chat_request = make_chat_request(PROMPT_NETTOYAGE,text_to_embed_clean)
        # 🔥 Cette ligne reste async - pas de changement !
        raw_response_dict = await llm_client.get_llm_chat_response(chat_request)

        response_details = raw_response_dict.get('response', {})
        usage_details = response_details.get('usage', {})
        error_details = response_details.get('error', {})
        state_llm = 1 if not error_details else 2

        doc_url = (document_data.get("fichier_source") or "").replace(r"\/", "/")
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

        raw_text = raw_response_dict.get('full_message', '')
        match = re.search(r'\{.*\}', raw_text, re.DOTALL)
        if match:
            json_string = match.group(0)
            json_string = re.sub(r'\\(?!["\\/bfnrtu])', r'\\\\', json_string)
            try:
                parsed_json = json.loads(json_string)
            except json.JSONDecodeError as je:
                logger.warning("JSON parse failed after escape sanitization: %s", je)
                parsed_json = {"contenu": "ok"}
            contenu = parsed_json.get("contenu")
            if not contenu:
                cleaned_text = ""
            if contenu != "ok":
                cleaned_text = contenu

    except Exception as e:
        logger.warning("Erreur lors du nettoyage LLM : %s - %s", type(e).__name__, e)
        error_str = f"Erreur lors du nettoyage LLM. Erreur: {e}"
        if not metric_payload:
            metric_payload = {
                "source_service": "nettoyage-bruit-ocr-service",
                "url": document_data.get('document'),
                "state_llm": 2,
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
        "metric_payload": metric_payload,
        "error_message": "le texte OCR nettoyé est vide" if not cleaned_text else ""
    }


async def nettoyer_bruits_ocr(documents: List[Dict]) -> List[Dict]:    
    """
    Exécute le traitement de chaque message dans un thread séparé.
    Cela libère l'event loop principal pour RabbitMQ.
    """
    if not documents:
        return []

    loop = asyncio.get_running_loop()

    tasks = [
        loop.run_in_executor(
            _thread_pool,
            _run_async_in_thread,
            _process_single_message(msg)
        )
        for msg in documents
    ]
    
    # 🔥 L'event loop principal reste libre pendant que les threads travaillent
    processed_results = await asyncio.gather(*tasks)
        
    logger.info("Nettoyage des bruits OCR en batch terminee pour %d messages.", len(processed_results))
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
            logger.info("[SUCCESS] URL: %s => Type: %s [Model: %s, PromptTokens: %s, CompletionTokens: %s, ContentLen: %s]", url, page_type, model, prompt_tokens, completion_tokens, content_len)
        else:
            logger.warning("[FAILURE] URL: %s => Erreur: %s", url, res.get('error_message', 'Inconnue'))
            
    return processed_results