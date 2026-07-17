import os
import logging
from typing import List, Dict
import urllib.parse
import httpx

from common_utils.autres.CollectionName import CollectionName
from common_utils.cleaner.CleanHTML import CleanHTML
from common_utils.cleaner.AnonymizeText import AnonymizeText
from common_utils.ocr.DeepseekOCRDocExtractor import DeepseekOCRDocExtractor

# Transient error types that should be retried, not sent to DLQ
_TRANSIENT_EXCEPTIONS = (
    httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout,
    httpx.WriteTimeout, httpx.PoolTimeout, ConnectionError, TimeoutError,
)

logger = logging.getLogger(__name__)

MAX_PAGES = 20

async def process_document_data_for_templating(documents: List[Dict], bdd: str = "milvus") -> List[Dict]:    
    anonymize = AnonymizeText()
    extractor = DeepseekOCRDocExtractor()
    
    # Structure pour maintenir l'ordre des documents
    # Chaque entrée contiendra le résultat final pour le document à cet index
    results_by_index: Dict[int, Dict] = {}
    
    # Liste de tuples (index_original, file_content, filename, document_item) pour les documents valides
    valid_files_data = []
    
    # Étape 1: Pré-validation de chaque document individuellement
    for index, document in enumerate(documents):
        document_data = document.get("data", {})
        
        raw_url = document_data.get("document")
        
        if not raw_url:
            # Document sans URL -> erreur pour DLQ (conserver l'index)
            results_by_index[index] = {
                "status": "error",
                "error_message": "Document sans URL de fichier",
                "processed_message": {
                    "text": "",
                    "len": 0,
                    "nb_pages": 0
                }
            }
            continue
            
        # Validate URL protocol before attempting download
        if not raw_url.startswith(("http://", "https://")):
            results_by_index[index] = {
                "status": "error",
                "error_message": "URL invalide: protocole http(s) manquant",
                "processed_message": {"text": "", "len": 0, "nb_pages": 0}
            }
            continue

        encoded_url = urllib.parse.quote(raw_url, safe=":/?&=")

        # Validation individuelle du document (téléchargement + vérification nb pages)
        try:
            file_content, filename = await extractor._download_file(encoded_url)
            extractor._validate_pdf_page_count(file_content, filename)

            valid_files_data.append((index, file_content, filename, document))
            logger.info("Document valide: %s", os.path.basename(raw_url))

        except ValueError as e:
            # Document invalide (trop de pages, PDF corrompu) -> erreur permanente pour DLQ
            logger.warning("Document invalide: %s", e)
            results_by_index[index] = {
                "status": "error",
                "error_message": str(e),
                "processed_message": {"text": "", "len": 0, "nb_pages": 0}
            }
        except _TRANSIENT_EXCEPTIONS as e:
            # Transient error (connection, timeout) -> should be retried
            logger.warning("Erreur transitoire lors du telechargement: %s", e)
            results_by_index[index] = {
                "status": "transient_error",
                "error_message": f"Erreur transitoire: {type(e).__name__}",
                "processed_message": {"text": "", "len": 0, "nb_pages": 0}
            }
        except Exception as e:
            # Other error (HTTP 403/404, etc.) -> permanent DLQ
            logger.error("Erreur lors de la validation: %s", e)
            results_by_index[index] = {
                "status": "error",
                "error_message": str(e),
                "processed_message": {"text": "", "len": 0, "nb_pages": 0}
            }
    
    # Étape 2: Traiter uniquement les documents valides avec OCR (sans re-téléchargement)
    ocr_results = {}
    ocr_failed = False
    ocr_error_msg = ""
    ocr_is_transient = False
    ocr_raw_response = None

    if valid_files_data:
        try:
            logger.info("Traitement OCR de %d document(s) valide(s)...", len(valid_files_data))

            files_for_ocr = [(file_content, filename) for _, file_content, filename, _ in valid_files_data]

            response = await extractor.extract_from_files(files_for_ocr)
            ocr_raw_response = response
            ocr_results = extractor.get_clean_result(response)
            del response
        except _TRANSIENT_EXCEPTIONS as e:
            ocr_failed = True
            ocr_is_transient = True
            ocr_error_msg = f"Erreur transitoire OCR: {type(e).__name__}"
            logger.warning(ocr_error_msg)
        except Exception as e:
            ocr_failed = True
            ocr_error_msg = f"Erreur OCR: {type(e).__name__}: {e}"
            logger.error(ocr_error_msg)
        finally:
            for _, file_content, _, _ in valid_files_data:
                file_content.close()

    del extractor

    # Étape 3: Traiter les résultats OCR des documents valides
    success_count = 0
    error_count = len(results_by_index)

    for index, file_content, filename, document_item in valid_files_data:
        try:
            if "document" in document_item:
                document_data = document_item
            else:
                document_data = document_item.get("data", {})

            # Si l'OCR a échoué globalement
            if ocr_failed:
                status = "transient_error" if ocr_is_transient else "error"
                results_by_index[index] = {
                    "status": status,
                    "error_message": ocr_error_msg,
                    "processed_message": {"text": "", "len": 0, "nb_pages": 0}
                }
                error_count += 1
                continue

            if filename in ocr_results:
                texts = ocr_results[filename].get("text", "")
                nb_pages = ocr_results[filename].get("total_pages", 0)
            else:
                # OCR returned no result for this file — check raw response for error details
                ocr_error_detail = ""
                if ocr_raw_response and not ocr_raw_response.get("success"):
                    ocr_error_detail = ocr_raw_response.get("error", "")
                texts = ""
                nb_pages = 0

            if nb_pages >= MAX_PAGES or len(texts.strip()) < 200:
                error_detail = f"nb_pages={nb_pages}, text_len={len(texts.strip())}"
                if filename not in ocr_results:
                    error_detail = f"OCR sans resultat pour ce fichier. {ocr_error_detail}".strip()
                results_by_index[index] = {
                    "status": "error",
                    "error_message": f"Document rejete: {error_detail}",
                    "processed_message": {"text": texts, "len": len(texts), "nb_pages": nb_pages}
                }
                error_count += 1

            elif texts:
                cleaner = CleanHTML(texts)
                cleaned_text = cleaner.clean()

                anonymized_text = anonymize.anonymize_text(cleaned_text)
                text_to_embed_clean = anonymize.normalize_text(anonymized_text)

                output_message = {
                    "data": {
                        "text": text_to_embed_clean,
                        **{k.replace("-", "_"): v for k, v in document_data.items() if k not in ["document"]}
                    },
                    "collection": CollectionName.DOCUMENT,
                    "database": bdd,
                    "nb_pages": nb_pages
                }

                results_by_index[index] = {
                    "status": "success",
                    "processed_message": output_message
                }
                success_count += 1
            else:
                results_by_index[index] = {
                    "status": "error",
                    "error_message": "Aucun texte extrait",
                    "processed_message": {"text": "", "len": 0, "nb_pages": nb_pages}
                }
                error_count += 1

        except Exception as e:
            logger.error("Erreur lors de l'assemblage du resultat pour index %d: %s", index, e, exc_info=True)
            results_by_index[index] = {
                "status": "error",
                "error_message": f"Erreur assemblage resultat: {type(e).__name__}: {e}",
                "processed_message": {"text": "", "len": 0, "nb_pages": 0}
            }
            error_count += 1
    
    # Étape 4: Construire la liste de résultats dans l'ordre original des documents
    all_results = []
    for i in range(len(documents)):
        if i in results_by_index:
            all_results.append(results_by_index[i])
        else:
            # Sécurité : si un index manque, ajouter une erreur générique
            all_results.append({
                "status": "error",
                "error_message": "Erreur interne: résultat manquant pour ce document",
                "processed_message": {
                    "text": "",
                    "len": 0,
                    "nb_pages": 0
                }
            })
            error_count += 1
    
    logger.info("Document-Echange-Processor: %d succes, %d erreurs", success_count, error_count)
    return all_results