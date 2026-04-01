import os
import logging
from typing import List, Dict
import urllib.parse

from common_utils.autres.CollectionName import CollectionName
from common_utils.cleaner.CleanHTML import CleanHTML
from common_utils.cleaner.AnonymizeText import AnonymizeText
from common_utils.ocr.DeepseekOCRDocExtractor import DeepseekOCRDocExtractor

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
            
        # Encodage de l'URL pour gérer les caractères spéciaux (ex: 100% -> 100%25)
        # safe=":/?&=" préserve la structure de l'URL http://...
        encoded_url = urllib.parse.quote(raw_url, safe=":/?&=")
        nom_doc = os.path.basename(raw_url)
        
        # Validation individuelle du document (téléchargement + vérification nb pages)
        try:
            # Télécharger et valider le document
            file_content, filename = await extractor._download_file(encoded_url)
            extractor._validate_pdf_page_count(file_content, filename)
            
            # Si validation OK, conserver le fichier en mémoire pour l'OCR
            # NE PAS fermer file_content ici, il sera utilisé pour l'OCR
            valid_files_data.append((index, file_content, filename, document))
            logger.info(f"✅ Document valide: {nom_doc}")
            
        except ValueError as e:
            # Document invalide (trop de pages) -> erreur pour DLQ
            error_msg = str(e)
            logger.warning(f"❌ Document invalide: {nom_doc} - {error_msg}")
            
            results_by_index[index] = {
                "status": "error",
                "error_message": f"Validation échouée pour '{nom_doc}': {error_msg}",
                "processed_message": {
                    "text": "",
                    "len": 0,
                    "nb_pages": 0
                }
            }
        except Exception as e:
            # Autre erreur (téléchargement, etc.) -> erreur pour DLQ
            error_msg = str(e)
            logger.error(f"❌ Erreur lors de la validation de {nom_doc}: {error_msg}")
            
            results_by_index[index] = {
                "status": "error",
                "error_message": f"Erreur de validation pour '{nom_doc}': {error_msg}",
                "processed_message": {
                    "text": "",
                    "len": 0,
                    "nb_pages": 0
                }
            }
    
    # Étape 2: Traiter uniquement les documents valides avec OCR (sans re-téléchargement)
    ocr_results = {}
    ocr_failed = False
    ocr_error_msg = ""
    
    if valid_files_data:
        try:
            logger.info(f"🔄 Traitement OCR de {len(valid_files_data)} document(s) valide(s)...")
            
            # Préparer les données pour extract_from_files (file_content, filename)
            files_for_ocr = [(file_content, filename) for _, file_content, filename, _ in valid_files_data]
            
            # Utiliser extract_from_files au lieu de extract_from_urls (pas de re-téléchargement)
            response = await extractor.extract_from_files(files_for_ocr)
            ocr_results = extractor.get_clean_result(response)
            del response
        except Exception as e:
            # Si l'OCR échoue pour le batch, tous les documents valides deviennent des erreurs
            ocr_failed = True
            ocr_error_msg = str(e)
            logger.error(f"❌ Erreur OCR batch: {ocr_error_msg}")
        finally:
            # Fermer tous les fichiers en mémoire après traitement OCR
            for _, file_content, _, _ in valid_files_data:
                file_content.close()
    
    # Libération immédiate des ressources lourdes OCR
    del extractor
    
    # Étape 3: Traiter les résultats OCR des documents valides
    success_count = 0
    error_count = len(results_by_index)  # Compteur d'erreurs déjà enregistrées
    
    for index, file_content, filename, document_item in valid_files_data:
        # Support des deux structures de message
        if "document" in document_item:
            document_data = document_item
        else:
            document_data = document_item.get("data", {})
        nom_doc = os.path.basename(document_data.get("document", "inconnu"))
        
        # Si l'OCR a échoué globalement, marquer tous les documents valides comme erreur
        if ocr_failed:
            results_by_index[index] = {
                "status": "error",
                "error_message": f"Erreur OCR pour '{nom_doc}': {ocr_error_msg}",
                "processed_message": {
                    "text": "",
                    "len": 0,
                    "nb_pages": 0
                }
            }
            error_count += 1
            continue
        
        if filename in ocr_results:
            texts = ocr_results.get(filename).get("text", "")
            nb_pages = ocr_results.get(filename).get("total_pages")
        else:
            texts = ""
            nb_pages = 0

        if nb_pages >= MAX_PAGES or len(texts.strip()) < 200:
            results_by_index[index] = {
                "status": "error",
                "error_message": f"Doc à ne pas traiter : nb_pages = {nb_pages} | len = {len(texts.strip())}",
                "processed_message": {
                    "text": texts,
                    "len": len(texts),
                    "nb_pages": nb_pages
                }
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
            # Cas où texts est vide mais pas capturé par la condition précédente
            results_by_index[index] = {
                "status": "error",
                "error_message": f"Aucun texte extrait pour '{nom_doc}'",
                "processed_message": {
                    "text": "",
                    "len": 0,
                    "nb_pages": nb_pages
                }
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
    
    logger.info(f"🔍 Document-Echange-Processor: {success_count} succès, {error_count} erreurs")
    return all_results