from common_utils.database.QdrantDevisCrud import QdrantDevisCrud
from common_utils.database.MilvusDevisCrud import MilvusDevisCrud
from common_utils.database.MilvusDevisInserer import MilvusDevisInserer

from common_utils.autres.CollectionName import CollectionName
import logging
from datetime import datetime

def insertion_data(devis_data: dict) -> dict:
    """
    Prend toutes les resultats de l'embedding puis ensuite inserer les chunk sur bdd vectoriel
    
    Retourne: Un dictionnaire prêt à être publié.
    """

    devis = devis_data.get("data",[])
    collection = devis_data.get("collection", CollectionName.DEVIS)
    bdd = devis_data.get("database", "qdrant")

    try:
        collection_enum = CollectionName(collection)
    except ValueError:
        logging.error("'%s' n'est pas un nom de collection valide.", collection)
        return None


    if(bdd.lower() == "milvus"):
        base_vectorielle = MilvusDevisCrud()
    else:
        base_vectorielle = QdrantDevisCrud()

    processing_functions = {
        CollectionName.DEVIS: base_vectorielle.insert_devis,
    }

    func = processing_functions.get(collection_enum)
    result = []
    if func and len(devis) > 0:
        lead_id = devis[0].get("lead_id", "lead_id inconnu")
        res = base_vectorielle.get_devis(lead_id=lead_id)
        correspondance_devis = MilvusDevisInserer()

        status = res.get("status")
        data   = res.get("data", [])
        code   = res.get("code", None)
        message = res.get("message", "")
        data_bo_milvus = []

        if status == "error":
            if code == 404:
                result = func(devis)
                output_message = {
                    "database"       : bdd,
                    "collection"     : collection,
                    "data"           : result,
                    "lead_id"        : lead_id,
                    "already_in_bdd" : len(data) > 0
                }
                data_bo_milvus.append({
                    "embedding"        : [0.0]*1024,
                    "id_devis_milvus"  : result.get("ids", ""),
                    "lead_id"          : lead_id,
                    "date_ajout"       : datetime.now().isoformat(),
                    "date_maj"         : ""
                })

            else:
                logging.error("Erreur lors de la vérification de Lead ID  %s : %s", lead_id, message)
                output_message = {
                    "database"       : bdd,
                    "collection"     : collection,
                    "data"           : [],
                    "lead_id"        : lead_id,
                    "error"          : message
                }

        elif status == "success":
            if len(data) > 0:
                logging.info("La lead_id %s existe déjà dans la base de données. Insertion ignorée.", lead_id)
                result = data
            else:
                result = func(devis)
                data_bo_milvus.append({
                    "embedding"      : [0.0]*1024,
                    "id_devis_milvus": result.get("ids", ""),
                    "lead_id"        : lead_id,
                    "date_ajout"     : datetime.now().isoformat(),
                    "date_maj"       : ""
                })

            output_message = {
                "database"        : bdd,
                "collection"      : collection,
                "data"            : result,
                "lead_id"         : lead_id,
                "already_in_bdd"  : len(data) > 0
            }

        if len(data_bo_milvus) > 0 and bdd == "milvus":
            correspondance_devis.insert_correspondance_devis(data_bo_milvus)

        return output_message