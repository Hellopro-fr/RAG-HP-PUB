from common_utils.database.QdrantProduitCrud import QdrantProduitsCrud
from common_utils.database.MilvusProduitCrud import MilvusProduitsCrud

from common_utils.autres.CollectionName import CollectionName
import logging

def insertion_data(produits_data: dict) -> dict:
    """
    Prend toutes les resultats de l'embedding puis ensuite inserer les chunk sur bdd vectoriel
    
    Retourne: Un dictionnaire prêt à être publié.
    """

    produits = produits_data.get("data",[])
    collection = produits_data.get("collection", CollectionName.PRODUIT)
    bdd = produits_data.get("database", "qdrant")

    try:
        collection_enum = CollectionName(collection)
    except ValueError:
        logging.error("'%s' n'est pas un nom de collection valide.", collection)
        return None


    if(bdd.lower() == "milvus"):
        base_vectorielle = MilvusProduitsCrud()
    else:
        base_vectorielle = QdrantProduitsCrud()

    processing_functions = {
        CollectionName.PRODUIT: base_vectorielle.insert_produits,
    }

    func = processing_functions.get(collection_enum)
    result = []
    if func:
        for cat in produits:
            id_produit = cat.get('id_produit', 'ID Demande inconnu')
            chunk        = cat.get('chunk_number', 'Numero chunk inconnu')
            total        = cat.get('total_chunks', 'Total chunk inconnu')
            logging.info("   ✅ Traitement réussi pour l'item '%s' - %s / %s.", id_produit, chunk, total)
            result.append(func(cat))
            
    
    output_message = {
        "collection": collection,
        "data"      : result,
        "id_produit": id_produit,
        "database" : bdd
    }
    
    return output_message