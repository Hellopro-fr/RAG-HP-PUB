import json
import time
import logging
import tldextract

from bs4 import BeautifulSoup

from common_utils.autres.CollectionName import CollectionName
from common_utils.cleaner.TrafilaturaCleaning import TrafilaturaHp
from common_utils.extractor.HeaderFooterExtractor import HeaderFooterExtractor
from website_processor_service.core.redis_manager import RedisManager

# Global Redis Manager instance
redis_manager = RedisManager()

def get_domain_from_url(url: str) -> str:
    """Extracts the registered domain (e.g., 'google.com') from a URL."""
    if not url: return "unknown"
    extracted = tldextract.extract(url)
    return f"{extracted.domain}.{extracted.suffix}"

def process_website_data_for_embedding(website_data: dict, bdd: str = "qdrant") -> dict:
    """
    Prend un dictionnaire de produit, le nettoie et prépare le message
    pour l’étape d’embedding.

    Retourne : Un dictionnaire prêt à être publié, ou NONE si en attente de batch.
    """
    # Étape 0: Initialisation
    output_message = {}
    log = "la vérification de template"
    url = website_data.get("url", "URL N/A")
    initial_content_size = len(website_data.get("text", ""))
    logging.info(f"[{url}] - Taille contenu initial: {initial_content_size} chars.")
    page_type = website_data.get("page_type", "")
    
    # Étape 1: Vérifier les données d'entrée
    if not isinstance(website_data, dict):
        raise ValueError("Les données doivent être un dictionnaire.")
    
    # Étape 2: HEADER / FOOTER TREATMENT (New Logic)
    if page_type in ["header", "footer"]:
        log = "l'embedding"
        domain = website_data.get("domaine", get_domain_from_url(url))
        raw_html = website_data.get("text", "")
        
        logging.info(f"[{url}] - Traitement Header/Footer ({page_type}) pour domaine: {domain}")
        
        # Buffer in Redis and check for batch
        batch_htmls = redis_manager.buffer_and_check_batch(domain, page_type, raw_html)
        
        if not batch_htmls:
            # STATUS: PENDING (Waiting for more pages)
            # We return a special signal to the consumer to just ACK and do nothing else.
            return {"status": "PENDING"}
        
        # STATUS: READY (Batch returned)
        logging.info(f"[{domain}] - Batch complet détecté. Lancement extraction Multi-Page.")
        
        try:
            # Instantiate Extractor with the first page (Main) 
            # Note: In a batch of 3 homogeneous pages, any can be main, but we use index 0.
            extractor = HeaderFooterExtractor(batch_htmls[0])
            
            # References are the other pages
            references = batch_htmls[1:]
            
            # Run the new robust extraction
            result = extractor.extract_with_fallback(references)
            
            # Extract the relevant part based on page_type
            extracted_text = result.get(page_type, "")
            method_used = result.get(f"{page_type}_method", "Unknown")
            
            if not extracted_text:
                raise ValueError(f"Aucun contenu extrait pour {page_type} via {method_used}")
            
            logging.info(f"[{domain}] - Extraction {page_type} réussie via {method_used}. Taille: {len(extracted_text)} chars.")
            
            text_to_embed_clean = extracted_text.strip()
            
        except Exception as e:
            raise ValueError(f"Erreur lors de l'extraction batch {page_type}: {e}")

    # Étape 3: STANDARD PAGE TREATMENT (Old Logic)
    else:  
        logging.info(f"[{url}] - Chemin de traitement: Contenu Principal (Trafilatura).")
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
                logging.info(
                    f"[{url}] - Extraction réussie avec Trafilatura Python (tentative {attempt + 1})")
                break
            if attempt < max_retries - 1:
                time.sleep(1)

        # 2. Fallback: Go-Trafilatura
        if not data_extracted:
            logging.info(
                f"[{url}] - Échec Trafilatura Python. Tentative avec Go-Trafilatura.")
            for attempt in range(max_retries):
                extracted_content = trafilatura.extract_go_trafilatura(
                    info.get("content", ""), url)
                if extracted_content and extracted_content.strip():
                    data_extracted = extracted_content
                    logging.info(
                        f"[{url}] - Extraction réussie avec Go-Trafilatura (tentative {attempt + 1})")
                    break
                if attempt < max_retries - 1:
                    time.sleep(1)

        # 3. Fallback: Boilerpy3
        if not data_extracted:
            logging.info(
                f"[{url}] - Échec Go-Trafilatura. Tentative avec Boilerpy3.")
            for attempt in range(max_retries):
                extracted_content = trafilatura.extract_boilerpy3(
                    info.get("content", ""))
                if extracted_content and extracted_content.strip():
                    data_extracted = extracted_content
                    logging.info(
                        f"[{url}] - Extraction réussie avec Boilerpy3 (tentative {attempt + 1})")
                    break
                if attempt < max_retries - 1:
                    time.sleep(1)

        if not data_extracted:
            raise ValueError(
                "Le contenu extrait est vide ou invalide après tous les essais (Trafilatura, Go, Boilerpy3).")
        
        logging.info(
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
    logging.info(f"[{url}] - Taille finale du texte nettoyé: {len(text_to_embed_clean)} chars. Prêt pour {log}.")
    
    # Étape 6: Retourner le message prêt à être publié
    logging.info(f"[{url}] - 📦 Website traité pour {log}.")
    return output_message