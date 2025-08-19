from common_utils.database.QdrantDevisCrud import QdrantDevisCrud
from common_utils.database.MilvusDevisCrud import MilvusDevisCrud

from common_utils.autres.CollectionName import CollectionName
import logging

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
    if func:
        for di in devis:
            id_di = di.get('lead_id', 'ID Demande inconnu')
            chunk = di.get('chunk_number', 'Numero chunk inconnu')
            total = di.get('total_chunks', 'Total chunk inconnu')
            logging.info("   ✅ Traitement réussi pour l'item '%s' - %s / %s.", id_di, chunk, total)
            result.append(func(di))
            
    
    output_message = {
        "collection": collection,
        "data"      : result,
        "id_demande": id_di
    }
    
    return output_message