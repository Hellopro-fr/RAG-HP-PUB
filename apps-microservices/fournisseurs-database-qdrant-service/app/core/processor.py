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
    if func and len(fournisseurs) > 0:
        id_fournisseur = fournisseurs[0].get('id_fournisseur', 'id_categorie inconnu')
        res = base_vectorielle.get_fournisseurs(id_fournisseur=id_fournisseur)
        
        status = res.get("status")
        data   = res.get("data", [])
        code   = res.get("code", None)
        message = res.get("message", "")
        
        if status == "error":
            if code == 404:
                result = func(fournisseurs)
                output_message = {
                    "database"      : bdd,
                    "collection"    : collection,
                    "data"          : result,
                    "id_fournisseur": id_fournisseur,
                    "already_in_bdd": len(data) > 0
                }
            else:
                logging.error("Erreur lors de la vérification de id_fournisseur  %s : %s", id_fournisseur, message)
                output_message = {
                    "database"      : bdd,
                    "collection"    : collection,
                    "data"          : [],
                    "id_fournisseur": id_fournisseur,
                    "error"         : message
                }
        elif status == "success":
            if len(data) > 0:
                logging.info("La id_fournisseur %s existe déjà dans la base de données. Insertion ignorée.", id_fournisseur)
                result = data
            else:
                result = func(fournisseurs)
                
            output_message = {
                "database"      : bdd,
                "collection"    : collection,
                "data"          : result,
                "id_fournisseur": id_fournisseur,
                "already_in_bdd": len(data) > 0
            }
    
        return output_message