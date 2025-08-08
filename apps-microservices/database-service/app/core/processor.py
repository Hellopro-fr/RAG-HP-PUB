from common_utils.database.MilvusCrud import MilvusCrud

from common_utils.autres.CollectionName import CollectionName
import logging


def insertion_data(product_data: dict) -> dict:
    """
    Prend toutes les resultats de l'embedding puis ensuite inserer les chunk sur bdd vectoriel
    
    Retourne: Un dictionnaire prêt à être publié.
    """

    products = product_data.get("data", {})
    collection = product_data.get("collection", "produits")

    try:
        collection_enum = CollectionName(collection)
    except ValueError:
        logging.error("'%s' n'est pas un nom de collection valide.", collection)
        return None

    milvus = MilvusCrud()
    processing_functions = {
        CollectionName.PRODUIT: milvus.insert_produit,
        # CollectionName.DEVIS: _process_devis,
        # CollectionName.CATEGORIE: _process_categorie,
        # CollectionName.FOURNISSEUR: _process_fournisseur,
        # CollectionName.ECHANGE: _process_echange,
    }

    func = processing_functions.get(collection_enum)
    result = []
    if func:
        for product in products:
            product_id = product.get('id_produit', 'ID inconnu')
            chunk = product.get('chunk_number', 'Numero chunk inconnu')
            total = product.get('total_chunks', 'Total chunk inconnu')
            logging.info("   ✅ Traitement réussi pour l'item '%s' - %s / %s.", product_id, chunk, total)
            result.append(func(product))
            
    
    output_message = {
        "collection": collection,
        "data": result,
        "id_produit": product_id
    }
    
    return output_message