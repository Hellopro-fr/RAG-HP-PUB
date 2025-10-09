from common_utils.database.QdrantEchangeCrud import QdrantEchangeCrud
from common_utils.database.MilvusEchangeCrud import MilvusEchangeCrud
from common_utils.database.MilvusEchangeInserer import MilvusEchangeInserer

from common_utils.autres.CollectionName import CollectionName
import logging
from datetime import datetime

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
    
    if func and len(echanges) > 0:
        conversation_id = echanges[0].get("conversation_id", "conversation_id inconnu")
        res = base_vectorielle.get_echange(conversation_id=conversation_id)
        correspondance_echange = MilvusEchangeInserer()

        status = res.get("status")
        data   = res.get("data", [])
        code   = res.get("code", None)
        message = res.get("message", "")
        data_bo_milvus = [] 

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
                data_bo_milvus.append({
                    "embedding"       : [0.0]*1024,
                    "id_echange_milvus": result.get("ids", ""),
                    "conversation_id"  : conversation_id,
                    "date_ajout"      : datetime.now().isoformat(),
                    "date_maj"        : ""
                })

                
            else:
                logging.error("Erreur lors de la vérification de conversation ID  %s : %s", conversation_id, message)
                output_message = {
                    "database"       : bdd,
                    "collection"     : collection,
                    "data"           : [],
                    "conversation_id": conversation_id,
                    "error"          : message
                }

        elif status == "success":
            if len(data) > 0:
                # Conversation existe déjà → MISE À JOUR
                logging.info("La conversation_id %s existe déjà. Mise à jour en cours...", conversation_id)

                if bdd.lower() == "milvus":
                    # Appeler la méthode update_echange qui gère toute la logique
                    result = base_vectorielle.update_echange(echanges, conversation_id, correspondance_echange)

                    if result.get("status") == "error":
                        logging.error("Erreur mise à jour pour %s: %s", conversation_id, result.get("message"))
                        output_message = {
                            "database"       : bdd,
                            "collection"     : collection,
                            "data"           : [],
                            "conversation_id": conversation_id,
                            "error"          : result.get("message")
                        }
                        return output_message

                    output_message = {
                        "database"        : bdd,
                        "collection"      : collection,
                        "data"            : result.get("data"),
                        "conversation_id" : conversation_id,
                        "already_in_bdd"  : result.get("already_in_bdd", True),
                        "updated"         : result.get("updated", True)
                    }
                else:
                    # Pour Qdrant, garder l'ancien comportement (skip)
                    logging.info("La conversation_id %s existe déjà dans la base de données. Insertion ignorée.", conversation_id)
                    result = data
                    output_message = {
                        "database"        : bdd,
                        "collection"      : collection,
                        "data"            : result,
                        "conversation_id" : conversation_id,
                        "already_in_bdd"  : True
                    }
            else:
                # Conversation n'existe pas → INSERTION NORMALE
                result = func(echanges)
                data_bo_milvus.append({
                    "embedding"       : [0.0]*1024,
                    "id_echange_milvus": result.get("ids", ""),
                    "conversation_id"  : conversation_id,
                    "date_ajout"       : datetime.now().isoformat(),
                    "date_maj"         : ""
                })

                output_message = {
                    "database"        : bdd,
                    "collection"      : collection,
                    "data"            : result,
                    "conversation_id" : conversation_id,
                    "already_in_bdd"  : False
                }

        if len(data_bo_milvus) > 0 and bdd.lower() == "milvus":
            correspondance_echange.insert_correspondance_echange(data_bo_milvus)
        
        return output_message