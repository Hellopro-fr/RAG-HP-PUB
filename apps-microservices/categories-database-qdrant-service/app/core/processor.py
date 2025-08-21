from common_utils.database.QdrantCategoriesCrud import QdrantCategoriesCrud
from common_utils.database.MilvusCategoriesCrud import MilvusCategoriesCrud

from common_utils.autres.CollectionName import CollectionName
import logging

def insertion_data(categories_data: dict) -> dict:
    """
    Prend toutes les resultats de l'embedding puis ensuite inserer les chunk sur bdd vectoriel
    
    Retourne: Un dictionnaire prêt à être publié.
    """

    categories = categories_data.get("data",[])
    collection = categories_data.get("collection", CollectionName.CATEGORIE)
    bdd = categories_data.get("database", "qdrant")

    try:
        collection_enum = CollectionName(collection)
    except ValueError:
        logging.error("'%s' n'est pas un nom de collection valide.", collection)
        return None


    if(bdd.lower() == "milvus"):
        base_vectorielle = MilvusCategoriesCrud()
    else:
        base_vectorielle = QdrantCategoriesCrud()

    processing_functions = {
        CollectionName.CATEGORIE: base_vectorielle.insert_categories,
    }

    func = processing_functions.get(collection_enum)
    result = []
    if func:
        for cat in categories:
            id_categorie = cat.get('id_categorie', 'ID Demande inconnu')
            chunk        = cat.get('chunk_number', 'Numero chunk inconnu')
            total        = cat.get('total_chunks', 'Total chunk inconnu')
            logging.info("   ✅ Traitement réussi pour l'item '%s' - %s / %s.", id_categorie, chunk, total)
            result.append(func(cat))
            
    
    output_message = {
        "collection": collection,
        "data"      : result,
        "id_categorie": id_categorie
    }
    
    return output_message