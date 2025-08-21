from common_utils.database.QdrantFournisseursCrud import QdrantFournisseursCrud
from common_utils.database.MilvusFournisseursCrud import MilvusFournisseursCrud

from common_utils.autres.CollectionName import CollectionName
import logging

def insertion_data(fournisseurs_data: dict) -> dict:
    """
    Prend toutes les resultats de l'embedding puis ensuite inserer les chunk sur bdd vectoriel
    
    Retourne: Un dictionnaire prêt à être publié.
    """

    fournisseurs = fournisseurs_data.get("data",[])
    collection = fournisseurs_data.get("collection", CollectionName.FOURNISSEUR)
    bdd = fournisseurs_data.get("database", "qdrant")

    try:
        collection_enum = CollectionName(collection)
    except ValueError:
        logging.error("'%s' n'est pas un nom de collection valide.", collection)
        return None


    if(bdd.lower() == "milvus"):
        base_vectorielle = MilvusFournisseursCrud()
    else:
        base_vectorielle = QdrantFournisseursCrud()

    processing_functions = {
        CollectionName.FOURNISSEUR: base_vectorielle.insert_fournisseurs,
    }

    func = processing_functions.get(collection_enum)
    result = []
    if func:
        for frs in fournisseurs:
            id_fournisseur = frs.get('id_fournisseur', 'ID Demande inconnu')
            chunk          = frs.get('chunk_number', 'Numero chunk inconnu')
            total          = frs.get('total_chunks', 'Total chunk inconnu')
            logging.info("   ✅ Traitement réussi pour l'item '%s' - %s / %s.", id_fournisseur, chunk, total)
            result.append(func(frs))
            
    
    output_message = {
        "collection"    : collection,
        "data"          : result,
        "id_fournisseur": id_fournisseur
    }
    
    return output_message