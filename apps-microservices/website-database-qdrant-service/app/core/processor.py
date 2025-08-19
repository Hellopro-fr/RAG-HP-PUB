from common_utils.database.QdrantWebsiteCrud import QdrantWebsiteCrud

from common_utils.autres.CollectionName import CollectionName
import logging

def insertion_data(website_data: dict) -> dict:
    """
    Prend toutes les resultats de l'embedding puis ensuite inserer les chunk sur bdd vectoriel
    
    Retourne: Un dictionnaire prêt à être publié.
    """

    websites = website_data.get("data",[])
    collection = website_data.get("collection", CollectionName.SITEWEB)

    try:
        collection_enum = CollectionName(collection)
    except ValueError:
        logging.error("'%s' n'est pas un nom de collection valide.", collection)
        return None

    qdrant = QdrantWebsiteCrud()
    processing_functions = {
        CollectionName.SITEWEB: qdrant.insert_website,
    }

    func = processing_functions.get(collection_enum)
    result = []
    if func:
        for website in websites:
            #Todo: à verifier
            url            = website.get('url', 'Url inconnu')
            chunk          = website.get('chunk_number', 'Numero chunk inconnu')
            total          = website.get('total_chunks', 'Total chunk inconnu')
            logging.info("   ✅ Traitement réussi pour l'item '%s' - %s / %s.", url, chunk, total)
            result.append(func(website))
            
    
    output_message = {
        "collection" : collection,
        "data"       : result,
        "url"        : url,
    }
    
    return output_message