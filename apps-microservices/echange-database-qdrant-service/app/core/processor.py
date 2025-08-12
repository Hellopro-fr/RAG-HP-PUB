from common_utils.database.QdrantEchangeCrud import QdrantEchangeCrud

from common_utils.autres.CollectionName import CollectionName
import logging

def insertion_data(echange_data: dict) -> dict:
    """
    Prend toutes les resultats de l'embedding puis ensuite inserer les chunk sur bdd vectoriel
    
    Retourne: Un dictionnaire prêt à être publié.
    """

    echanges = echange_data.get("data",[])
    collection = echange_data.get("collection", CollectionName.ECHANGE)

    try:
        collection_enum = CollectionName(collection)
    except ValueError:
        logging.error("'%s' n'est pas un nom de collection valide.", collection)
        return None

    qdrant = QdrantEchangeCrud()
    processing_functions = {
        CollectionName.ECHANGE: qdrant.insert_echange,
    }

    func = processing_functions.get(collection_enum)
    result = []
    if func:
        for echange in echanges:
            id_di          = echange.get('id_demande', 'ID Demande inconnu')
            id_fournisseur = echange.get('id_fournisseur', 'ID Fournisseur inconnu')
            id_acheteur    = echange.get('id_acheteur', 'ID Acheteur inconnu')
            chunk          = echange.get('chunk_number', 'Numero chunk inconnu')
            total          = echange.get('total_chunks', 'Total chunk inconnu')
            logging.info("   ✅ Traitement réussi pour l'item '%s' - %s / %s.", id_di, id_fournisseur, id_acheteur, chunk, total)
            result.append(func(echange))
            
    
    output_message = {
        "collection"     : collection,
        "data"           : result,
        "id_demande"     : id_di,
        "id_fournisseur" : id_fournisseur,
        "id_acheteur"    : id_acheteur
    }
    
    return output_message