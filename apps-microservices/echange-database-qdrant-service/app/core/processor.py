from common_utils.database.QdrantEchangeCrud import QdrantEchangeCrud
from common_utils.database.MilvusEchangeCrud import MilvusEchangeCrud

from common_utils.autres.CollectionName import CollectionName
import logging

def insertion_data(echange_data: dict) -> dict:
    """
    Prend toutes les resultats de l'embedding puis ensuite inserer les chunk sur bdd vectoriel
    
    Retourne: Un dictionnaire prêt à être publié.
    """

    echanges = echange_data.get("data",[])
    collection = echange_data.get("collection", CollectionName.ECHANGE)
    bdd = echange_data.get("database", "qdrant")

    try:
        collection_enum = CollectionName(collection)
    except ValueError:
        logging.error("'%s' n'est pas un nom de collection valide.", collection)
        return None

    if(bdd.lower() == "milvus"):
        base_vectorielle = MilvusEchangeCrud()
    else:
        base_vectorielle = QdrantEchangeCrud()


    processing_functions = {
        CollectionName.ECHANGE: base_vectorielle.insert_echange,
    }

    func = processing_functions.get(collection_enum)
    result = []
    
    if func:
        conversation_id = echanges[0].get("conversation_id", "conversation_id inconnu")
        res = base_vectorielle.get_echange(conversation_id=conversation_id)

        status = res.get("status")
        data   = res.get("data", [])
        code   = res.get("code", None)
        message = res.get("message", "")

        if status == "error":
            if code == 404:
                result = func(echanges)
                output_message = {
                    "database"       : bdd,
                    "collection"     : collection,
                    "data"           : result,
                    "conversation_id": conversation_id,
                    "already_in_bdd" : len(data) > 0
                }
            else:
                logging.error("Erreur lors de la vérification de l'URL %s : %s", url, message)
                output_message = {
                    "database"       : bdd,
                    "collection"     : collection,
                    "data"           : [],
                    "conversation_id": conversation_id,
                    "error"          : message
                }

        elif status == "success":
            if len(data) > 0:
                logging.info("L'URL %s existe déjà dans la base de données. Insertion ignorée.", url)
                result = data
            else:
                result = func(echanges)

            output_message = {
                "database"        : bdd,
                "collection"      : collection,
                "data"            : result,
                "conversation_id" : conversation_id,
                "already_in_bdd"  : len(data) > 0
            }

        return output_message