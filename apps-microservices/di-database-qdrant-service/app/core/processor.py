from common_utils.database.QdrantDevisCrud import QdrantDevisCrud

from common_utils.autres.CollectionName import CollectionName
import logging

def insertion_data(devis_data: dict) -> dict:
    """
    Prend toutes les resultats de l'embedding puis ensuite inserer les chunk sur bdd vectoriel
    
    Retourne: Un dictionnaire prêt à être publié.
    """

    devis = devis_data.get("data", {})
    collection = devis_data.get("collection", CollectionName.DEVIS)

    try:
        collection_enum = CollectionName(collection)
    except ValueError:
        logging.error("'%s' n'est pas un nom de collection valide.", collection)
        return None

    qdrant = QdrantDevisCrud()
    processing_functions = {
        CollectionName.DEVIS: qdrant.insert_devis,
    }

    func = processing_functions.get(collection_enum)
    result = []
    if func:
        for di in devis:
            di_id = di.get('id_demande', 'ID inconnu')
            chunk = di.get('chunk_number', 'Numero chunk inconnu')
            total = di.get('total_chunks', 'Total chunk inconnu')
            logging.info("   ✅ Traitement réussi pour l'item '%s' - %s / %s.", di_id, chunk, total)
            result.append(func(di))
            
    
    output_message = {
        "collection": collection,
        "data": result,
        "id": di_id
    }
    
    return output_message