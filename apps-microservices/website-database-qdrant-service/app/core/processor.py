from common_utils.database.QdrantWebsiteCrud import QdrantWebsiteCrud
from common_utils.database.MilvusWebsiteCrud import MilvusWebsiteCrud

from common_utils.autres.CollectionName import CollectionName
import logging

def insertion_data(website_data: dict) -> dict:
    """
    Prend toutes les resultats de l'embedding puis ensuite inserer les chunk sur bdd vectoriel
    
    Retourne: Un dictionnaire prêt à être publié.
    """

    websites = website_data.get("data",[])
    collection = website_data.get("collection", CollectionName.SITEWEB)
    bdd = website_data.get("database", "qdrant") 

    try:
        collection_enum = CollectionName(collection)
    except ValueError:
        logging.error("'%s' n'est pas un nom de collection valide.", collection)
        return None

    if(bdd.lower() == "milvus"):
        base_vectorielle = MilvusWebsiteCrud()
    else:
        base_vectorielle = QdrantWebsiteCrud()

    processing_functions = {
        CollectionName.SITEWEB: base_vectorielle.insert_website

    }

    func = processing_functions.get(collection_enum)
    
    result = []
    url = ""

    if func:
        url = websites[0].get("url", "Url inconnu")
        res = base_vectorielle.get_website(url=url)

        status = res.get("status")
        data   = res.get("data", [])
        code   = res.get("code", None)
        message = res.get("message", "")

        if status == "error":
            if code == 404:
                result = func(websites)
                output_message = {
                    "database"       : bdd,
                    "collection"     : collection,
                    "data"           : result,
                    "url"            : url,
                    "already_in_bdd" : len(data) > 0
                }
            else:
                logging.error("Erreur lors de la vérification de l'URL %s : %s", url, message)
                output_message = {
                    "database"   : bdd,
                    "collection" : collection,
                    "data"       : [],
                    "url"        : url,
                    "error"      : message
                }

        elif status == "success":
            if len(data) > 0:
                logging.info("L'URL %s existe déjà dans la base de données. Insertion ignorée.", url)
                result = data
            else:
                result = func(websites)

            output_message = {
                "database"       : bdd,
                "collection"     : collection,
                "data"           : result,
                "url"            : url,
                "already_in_bdd" : len(data) > 0
            }

        return output_message
