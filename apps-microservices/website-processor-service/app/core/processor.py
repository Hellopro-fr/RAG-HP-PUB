import json
import time
import logging
import tldextract

from bs4 import BeautifulSoup

from common_utils.autres.CollectionName import CollectionName
from common_utils.cleaner.TrafilaturaCleaning import TrafilaturaHp
from common_utils.extractor.HeaderFooterExtractor import HeaderFooterExtractor
from website_processor_service.core.redis_manager import RedisManager
from website_processor_service.core.exceptions import BatchProcessingError

logger = logging.getLogger(__name__)

# Global Redis Manager instance
redis_manager = RedisManager()

def get_domain_from_url(url: str) -> str:
    """Extracts the registered domain (e.g., 'google.com') from a URL."""
    if not url: return "unknown"
    extracted = tldextract.extract(url)
    return f"{extracted.domain}.{extracted.suffix}"

def _check_existing_classification(url: str, domaine: str) -> str | None:
    """
    Vérifie si l'URL existe déjà dans la base vectorielle (Milvus) et récupère son page_type.
    Utilisé pour le bypass du template-llm-service : si la page est déjà classifiée,
    on réutilise la classification existante au lieu de refaire un appel LLM.

    Note: L'import de MilvusWebsiteCrud est fait en lazy car pymilvus n'est pas
    installé dans le conteneur website-processor-service. Si le module est absent,
    le bypass est simplement désactivé et la page suit le flux normal.

    Args:
        url: L'URL de la page web.
        domaine: Le domaine extrait de l'URL.

    Returns:
        Le page_type existant (str) si trouvé, None sinon.
    """
    try:
        from common_utils.database.MilvusWebsiteCrud import MilvusWebsiteCrud
    except ImportError:
        logger.warning(f"[{url}] - pymilvus non disponible, bypass désactivé.")
        return None

    try:
        base_vectorielle = MilvusWebsiteCrud()

        # On passe un page_type fictif non-header/footer pour déclencher la recherche par URL
        res = base_vectorielle.get_website(url=url, page_type="lookup", domaine=domaine)
        
        if res and res.get("status") == "success":
            data = res.get("data", [])
            if data and len(data) > 0:
                # Récupérer le page_type du premier résultat
                existing_page_type = data[0].get("page_type")
                if existing_page_type and existing_page_type not in ["header", "footer"]:
                    logger.info(f"[{url}] - ⚡ Bypass: Classification existante trouvée: '{existing_page_type}'")
                    return existing_page_type

    except Exception as e:
        # En cas d'erreur, on ne bloque pas le flux normal.
        # On laisse le message passer par le template-llm-service.
        logger.warning(f"[{url}] - Bypass check échoué (non-bloquant): {e}")
    
    return None

def process_website_data_for_embedding(website_data: dict, bdd: str = "qdrant") -> dict:
    """
    Prend un dictionnaire de produit, le nettoie et prépare le message
    pour l'étape d'embedding.

    Retourne : Un dictionnaire prêt à être publié, ou message avec status='PENDING'.
    Raises : BatchProcessingError si l'extraction batch échoue (pour DLQ).
    """
    # Étape 0: Initialisation
    output_message = {}
    log = "la vérification de template"
    url = website_data.get("url", "URL N/A")
    initial_content_size = len(website_data.get("text", ""))
    logger.info(f"[{url}] - Taille contenu initial: {initial_content_size} chars.")
    page_type = website_data.get("page_type", "")
    
    # Étape 1: Vérifier les données d'entrée
    if not isinstance(website_data, dict):
        raise ValueError("Les données doivent être un dictionnaire.")
    
    # Étape 2: HEADER / FOOTER TREATMENT (New Logic)
    if page_type in ["header", "footer"]:
        log = "l'embedding"
        domain = website_data.get("domaine", get_domain_from_url(url))
        
        # Serialize the FULL original message structure to store in Redis.
        # This preserves 'database' and all outer keys, allowing us to resurrect
        # complete messages to the DLQ if the batch processing fails later.
        full_payload = {
            "data": website_data,
            "database": bdd,
            "collection": "siteweb",
            "origin": ""
        }
        payload_str = json.dumps(full_payload)
        
        logger.info(f"[{url}] - Traitement Header/Footer ({page_type}) pour domaine: {domain}")
        
        # Buffer in Redis and check for batch
        batch_json_strings = redis_manager.buffer_and_check_batch(domain, page_type, payload_str)
        
        if not batch_json_strings:
            # STATUS: PENDING (Waiting for more pages)
            return {"status": "PENDING"}
        
        # STATUS: READY (Batch returned)
        logger.info(f"[{domain}] - Batch complet détecté. Lancement extraction Multi-Page.")
        
        # Deserialize the batch
        # Each item is a full message: {"data": website_data, "database": bdd, "collection": "siteweb", "origin": ""}
        batch_payloads = []
        try:
            batch_payloads = [json.loads(s) for s in batch_json_strings]
        except json.JSONDecodeError as e:
            # Critical corruption in Redis data
            logger.error(f"Failed to decode batch from Redis: {e}")
            raise ValueError("Corrupted batch data in Redis")

        try:
            # Extract the inner website_data dicts for processing
            batch_website_data = [d.get("data", d) for d in batch_payloads]
            
            # Extract HTML content from the website_data
            html_sources = [d.get("text", "") for d in batch_website_data]
            
            # Instantiate Extractor with the first page
            extractor = HeaderFooterExtractor(html_sources[0])
            
            # References are the other pages
            references = html_sources[1:]
            
            # Run the new robust extraction
            result = extractor.extract_with_fallback(references)
            
            # Extract the relevant part based on page_type
            extracted_text = result.get(page_type, "")
            method_used = result.get(f"{page_type}_method", "Unknown")
            
            if not extracted_text:
                raise ValueError(f"Aucun contenu extrait pour {page_type} via {method_used}")
            
            logger.info(f"[{domain}] - Extraction {page_type} réussie via {method_used}. Taille: {len(extracted_text)} chars.")
            
            text_to_embed_clean = extracted_text.strip()
            
        except Exception as e:
            # Extraction Failed! 
            # We need to send ALL messages in this batch to the DLQ.
            # The current message (website_data) will be handled by the consumer's standard exception handler.
            # But the OTHER messages in the batch were already ACKed. We must return them to the consumer for manual DLQing.
            
            # Filter out the current message to avoid double-DLQing
            # We use URL as a unique identifier (assuming 1 msg per URL per batch)
            # batch_payloads contains full messages {"data": {...}, "database": ...}
            previous_payloads = [
                d for d in batch_payloads 
                if d.get('data', {}).get('url') != website_data.get('url')
            ]
            
            raise BatchProcessingError(
                message=f"Échec extraction batch {page_type}: {str(e)}",
                previous_payloads=previous_payloads,
                original_error=e
            )

    # Étape 3: STANDARD PAGE TREATMENT
    else:
        # --- Étape 3.0: Bypass - Vérifier si la page a déjà été classifiée ---
        if not page_type:
            domaine = website_data.get("domaine", get_domain_from_url(url))
            existing_page_type = _check_existing_classification(url, domaine)
            if existing_page_type:
                # Injecter le page_type existant pour déclencher le bypass
                # Le consumer routera vers 'data.ready_for_embedding' au lieu de 'data.ready_for_templating'
                website_data["page_type"] = existing_page_type
                page_type = existing_page_type
                log = "l'embedding (bypass template-llm)"
                logger.info(f"[{url}] - ⚡ Bypass activé: réutilisation de la classification '{existing_page_type}'.")

        logger.info(f"[{url}] - Chemin de traitement: Contenu Principal (Trafilatura).")
        # Étape 3.1: Construction du dictionnaire d'entrée pour le nettoyage
        info = {
            "url": website_data.get("url",""),
            "content": website_data.get("text",""),
            "fetch": False
        }

        # Étape 3.2: Extraire le contenu nettoyé avec Trafilatura, avec une logique de retry et fallback
        trafilatura = TrafilaturaHp(info)
        data_extracted = ""
        max_retries = 3

        # 1. Trafilatura Python
        for attempt in range(max_retries):
            extracted_content = trafilatura.extract(info).content
            if extracted_content and extracted_content.strip():
                data_extracted = extracted_content
                logger.info(
                    f"[{url}] - Extraction réussie avec Trafilatura Python (tentative {attempt + 1})")
                break
            if attempt < max_retries - 1:
                time.sleep(1)

        # 2. Fallback: Go-Trafilatura
        if not data_extracted:
            logger.info(
                f"[{url}] - Échec Trafilatura Python. Tentative avec Go-Trafilatura.")
            for attempt in range(max_retries):
                extracted_content = trafilatura.extract_go_trafilatura(
                    info.get("content", ""), url)
                if extracted_content and extracted_content.strip():
                    data_extracted = extracted_content
                    logger.info(
                        f"[{url}] - Extraction réussie avec Go-Trafilatura (tentative {attempt + 1})")
                    break
                if attempt < max_retries - 1:
                    time.sleep(1)

        # 3. Fallback: Boilerpy3
        if not data_extracted:
            logger.info(
                f"[{url}] - Échec Go-Trafilatura. Tentative avec Boilerpy3.")
            for attempt in range(max_retries):
                extracted_content = trafilatura.extract_boilerpy3(
                    info.get("content", ""))
                if extracted_content and extracted_content.strip():
                    data_extracted = extracted_content
                    logger.info(
                        f"[{url}] - Extraction réussie avec Boilerpy3 (tentative {attempt + 1})")
                    break
                if attempt < max_retries - 1:
                    time.sleep(1)

        if not data_extracted:
            raise ValueError(
                "Le contenu extrait est vide ou invalide après tous les essais (Trafilatura, Go, Boilerpy3).")
        
        logger.info(
            f"[{url}] - Taille texte extrait: {len(data_extracted)} chars.")
        text_to_embed_clean = data_extracted.strip()
    
    # Étape 4: Construire le message de sortie
    output_message = {
        "data": {
            "text": text_to_embed_clean,
            **{k.replace("-", "_"): v for k, v in website_data.items() if k not in ['text']}
        },
        "collection": CollectionName.SITEWEB,
        "database": bdd
    }

    # Étape 5: Afficher le message de sortie pour débogage
    logger.info(f"[{url}] - Taille finale du texte nettoyé: {len(text_to_embed_clean)} chars. Prêt pour {log}.")
    
    # Étape 6: Retourner le message prêt à être publié
    logger.info(f"[{url}] - 📦 Website traité pour {log}.")
    return output_message