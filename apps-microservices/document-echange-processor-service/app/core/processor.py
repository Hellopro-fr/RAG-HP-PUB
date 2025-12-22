import os
from typing import List, Dict
import urllib.parse

from common_utils.autres.CollectionName import CollectionName
from common_utils.cleaner.CleanHTML import CleanHTML
from common_utils.cleaner.AnonymizeText import AnonymizeText
from common_utils.ocr.DeepseekOCRDocExtractor import DeepseekOCRDocExtractor

async def process_document_data_for_templating(documents: List[Dict], bdd: str = "milvus") -> List[Dict]:    
    anonymize = AnonymizeText()
    extractor = DeepseekOCRDocExtractor()
    
    # Étape 1: Pré-validation de chaque document individuellement
    valid_files_data = []  # Liste de tuples (file_content, filename, document_item)
    invalid_results = []
    
    for document in documents:
        document_data = document.get("data", {}).get("original_data", {})
        raw_url = document_data.get("document")
        
        if not raw_url:
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
            valid_files_data.append((file_content, filename, document))
            print(f"✅ Document valide: {nom_doc}")
            
        except ValueError as e:
            # Document invalide (trop de pages) -> erreur pour DLQ
            error_msg = str(e)
            print(f"❌ Document invalide: {nom_doc} - {error_msg}")
            
            invalid_results.append({
                "status": "error",
                "error_message": f"Validation échouée pour '{nom_doc}': {error_msg}",
                "processed_message": {
                    "text": "",
                    "len": 0,
                    "nb_pages": 0
                }
            })
        except Exception as e:
            # Autre erreur (téléchargement, etc.) -> erreur pour DLQ
            error_msg = str(e)
            print(f"❌ Erreur lors de la validation de {nom_doc}: {error_msg}")
            
            invalid_results.append({
                "status": "error",
                "error_message": f"Erreur de validation pour '{nom_doc}': {error_msg}",
                "processed_message": {
                    "text": "",
                    "len": 0,
                    "nb_pages": 0
                }
            })
    
    # Étape 2: Traiter uniquement les documents valides avec OCR (sans re-téléchargement)
    results = {}
    if valid_files_data:
        try:
            print(f"🔄 Traitement OCR de {len(valid_files_data)} document(s) valide(s)...")
            
            # Préparer les données pour extract_from_files (file_content, filename)
            files_for_ocr = [(file_content, filename) for file_content, filename, _ in valid_files_data]
            
            # Utiliser extract_from_files au lieu de extract_from_urls (pas de re-téléchargement)
            response = await extractor.extract_from_files(files_for_ocr)
            results = extractor.get_clean_result(response)
            del response
        except Exception as e:
            # Si l'OCR échoue pour le batch, tous les documents valides deviennent des erreurs
            error_msg = str(e)
            print(f"❌ Erreur OCR batch: {error_msg}")
            
            for file_content, filename, document_item in valid_files_data:
                document_data = document_item.get("data", {}).get("original_data", {})
                nom_doc = os.path.basename(document_data.get("document", "inconnu"))
                
                invalid_results.append({
                    "status": "error",
                    "error_message": f"Erreur OCR pour '{nom_doc}': {error_msg}",
                    "processed_message": {
                        "text": "",
                        "len": 0,
                        "nb_pages": 0
                    }
                })
        finally:
            # Fermer tous les fichiers en mémoire après traitement OCR
            for file_content, _, _ in valid_files_data:
                file_content.close()
    
    # Libération immédiate des ressources lourdes OCR
    del extractor
    
    # Étape 3: Traiter les résultats OCR des documents valides
    processed_messages_result = []

    for file_content, filename, document_item in valid_files_data:
        output_message = {}
        document_data = document_item.get("data", {}).get("original_data", {})
        nom_doc = os.path.basename(document_data.get("document", "inconnu"))

        if filename in results:
            texts = results.get(filename).get("text", "")
            nb_pages = results.get(filename).get("total_pages")
            text_to_embed_clean = texts
        else:
            texts = ""
            nb_pages = 0

        if nb_pages >= 20 or len(texts.strip()) < 200:
            processed_messages_result.append({
                "status": "error",
                "error_message": f"Doc à ne pas traiter : nb_pages = {nb_pages} | len = {len(texts.strip())}",
                "processed_message": {
                    "text": texts,
                    "len": len(texts),
                    "nb_pages": nb_pages
                }
            })
            
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

            processed_messages_result.append({
                "status": "success",
                "processed_message": output_message
            })
    
    # Étape 4: Combiner les résultats valides et invalides
    all_results = invalid_results + processed_messages_result
    
    print(f"🔍Document-Echange-Processor: {len(processed_messages_result)} succès, {len(invalid_results)} erreurs")
    return all_results
    