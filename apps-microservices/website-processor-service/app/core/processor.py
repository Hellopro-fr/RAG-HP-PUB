import json
import time
import logging

from bs4 import BeautifulSoup

from common_utils.autres.CollectionName import CollectionName
from common_utils.cleaner.TrafilaturaCleaning import TrafilaturaHp
from common_utils.extractor.HeaderFooterExtractor import HeaderFooterExtractor


def process_website_data_for_embedding(website_data: dict, bdd: str = "qdrant") -> dict:
    """
    Prend un dictionnaire de produit, le nettoie et prépare le message
    pour l’étape d’embedding.

    Retourne : Un dictionnaire prêt à être publié.
    """
    # Étape 0: Initialisation du message de sortie
    output_message = {}
    log = "la vérification de template"
    url = website_data.get("url", "URL N/A")
    initial_content_size = len(website_data.get("text", ""))
    logging.info(f"[{url}] - Taille contenu initial: {initial_content_size} chars.")
    
    # Étape 1: Vérifier les données d'entrée
    if not isinstance(website_data, dict):
        raise ValueError("Les données doivent être un dictionnaire.")
    
    # Étape 2: Vérifier si la présence du page_type == "header" ou page_type == "footer" sinon on procède normalement
    if website_data.get("page_type","") == "header" or website_data.get("page_type","") == "footer":
        page_type = str(website_data.get("page_type",""))
        log = "l'embedding"
        logging.info(f"[{url}] - Chemin de traitement: Header/Footer ({page_type}).")
        # Étape 2.1: Extraire le header et footer
        try:
            extractor = HeaderFooterExtractor(website_data.get("text",""))
            if not isinstance(extractor.soup, BeautifulSoup):
                raise ValueError("Le contenu HTML est invalide ou vide.")
            
            if page_type == "header":
                text_to_embed = extractor.extract_header(extractor.soup)
                if not text_to_embed:
                    raise ValueError("Aucun header extrait.")
            else:
                text_to_embed = extractor.extract_footer(extractor.soup)
                if not text_to_embed:
                    raise ValueError("Aucun footer extrait.")
            
            logging.info(f"[{url}] - Taille texte extrait brut: {len(text_to_embed)} chars.")
            text_to_embed_clean = text_to_embed.strip()
        except Exception as e:
            raise ValueError(f"Erreur lors de l'extraction du {page_type.capitalize()}: {e}")
    else:  
        logging.info(f"[{url}] - Chemin de traitement: Contenu Principal (Trafilatura).")
        # Étape 2.1: Construction du dictionnaire d'entrée pour le nettoyage
        info = {
            "url": website_data.get("url",""),
            "content": website_data.get("text",""),
            "fetch": False
        }

        # Étape 2.2: Extraire le contenu nettoyé avec Trafilatura, avec une logique de retry et fallback
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
    
    # Étape 3: Construire le message de sortie
    output_message = {
        "data": {
            "text": text_to_embed_clean,
            # Todo: à modifier si nécessaire
            **{k.replace("-", "_"): v for k, v in website_data.items() if k not in ['text']}
        },
        "collection": CollectionName.SITEWEB,
        "database": bdd  
    }

    # Étape 4: Afficher le message de sortie pour débogage
    logging.info(f"[{url}] - Taille finale du texte nettoyé: {len(text_to_embed_clean)} chars. Prêt pour {log}.")
    
    # Étape 5: Retourner le message prêt à être publié
    logging.info(f"[{url}] - 📦 Website traité pour {log}.")
    return output_message