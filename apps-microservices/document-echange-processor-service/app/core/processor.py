import os
from typing import List, Dict

from common_utils.autres.CollectionName import CollectionName
from common_utils.cleaner.CleanHTML import CleanHTML
from common_utils.cleaner.AnonymizeText import AnonymizeText
from common_utils.ocr.DeepseekOCRDocExtractor import DeepseekOCRDocExtractor

async def process_document_data_for_templating(documents: List[Dict], bdd: str = "milvus") -> List[Dict]:    
    docs = []
    anonymize = AnonymizeText()

    for document in documents:
        document_data = document.get("data",{}).get("original_data",{})
        # document_data = document.get("data",{})
        docs.append(document_data.get("document"))

    extractor = DeepseekOCRDocExtractor()
    response = await extractor.extract_from_urls(docs)
    results = extractor.get_clean_result(response)
    
    processed_messages_result = []

    for document_item in documents:
        
        output_message = {}
        document_data = document_item.get("data",{}).get("original_data",{})
        # document_data = document_item.get("data",{})

        nom_doc = os.path.basename(document_data.get("document","inconnu"))

        if nom_doc in results:
            texts = results.get(nom_doc).get("text","")
            nb_pages = results.get(nom_doc).get("total_pages")
            text_to_embed_clean = texts
        else:
            texts = ""
            nb_pages = 0

        if nb_pages >= 20 or len(texts.strip()) < 200 :
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
            cleaner      = CleanHTML(texts)
            cleaned_text = cleaner.clean()

            anonymized_text     = anonymize.anonymize_text(cleaned_text)
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

    print(f"🔍Document-Echange-Processor: Message prêt")
    return processed_messages_result
    