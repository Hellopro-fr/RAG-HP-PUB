from common_utils.database.QdrantProduitCrud import QdrantProduitsCrud
from common_utils.database.MilvusProduitCrud import MilvusProduitsCrud
from common_utils.database.MilvusProduitInserer import MilvusProduitInserer

from common_utils.autres.CollectionName import CollectionName
import logging
from datetime import datetime

def insertion_data(produits_data: dict) -> dict:
    """
    Prend toutes les resultats de l'embedding puis ensuite inserer les chunk sur bdd vectoriel

    Logique d'insertion :
    - Si id_produit existe ET source existante = "BO" → Pas d'insertion
    - Si id_produit existe ET source existante ≠ "BO" → Insertion
    - Si id_produit n'existe pas → Insertion
    
    Retourne: Un dictionnaire prêt à être publié.
    """
    produits   = produits_data.get("data",[])
    collection = produits_data.get("collection", CollectionName.PRODUIT)
    bdd        = produits_data.get("database", "qdrant")
    origin     = produits_data.get("origin", "bo")

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

    if func and len(produits) > 0:
        id_produit = produits[0].get('id_produit', 'ID produit inconnu')
        res = base_vectorielle.get_produit(id_produit=id_produit)
        correspondance_produit = MilvusProduitInserer()

        status = res.get("status")
        data   = res.get("data", [])
        code   = res.get("code", None)
        message = res.get("message", "")
        data_bo_milvus = []

        if status == "error":
            if code == 404:
                result = func(produits)
                if not result:  # None, {}, ou False
                    id_produit_milvus = ""
                else:
                    id_produit_milvus = result.get("ids", "")
                output_message = {
                    "database"      : bdd,
                    "collection"    : collection,
                    "data"          : result,
                    "id_produit"    : id_produit,
                    "already_in_bdd": len(data) > 0,
                    "origin"        : origin
                }
                data_bo_milvus.append({
                    "embedding"       : [0.0]*1024,
                    "id_produit"       : id_produit,
                    "id_produit_milvus": result.get("ids", ""),
                    "date_ajout"       : datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "date_maj"         : "",
                    "origin"           : origin
                })
            else:
                logging.error("Erreur lors de la vérification du produit ID  %s : %s", id_produit, message)
                output_message = {
                    "database"  : bdd,
                    "collection": collection,
                    "data"      : [],
                    "id_produit": id_produit,
                    "error"     : message,
                    "origin"        : origin
                }

        elif status == "success":
            if len(data) > 0:
                #recuperer la source du produit existant en base
                existing_sources = [item.get('source', '') for item in data]
                existing_sources_set = set(existing_sources)

                 # Vérifier si BO existe ou si les deux sources BO et SITEWEB existent
                has_bo = "BO" in existing_sources_set
                has_siteweb = "SITEWEB" in existing_sources_set
                has_both_bo_and_siteweb = has_bo and has_siteweb

                if has_bo or has_both_bo_and_siteweb:
                    # Cas où on ne doit pas insérer
                    if has_both_bo_and_siteweb:
                        reason = "les deux sources BO et SITEWEB existent déjà"
                    else:
                        reason = "source BO existe déjà"
                        
                    print(f"Le produit ID {id_produit} : {reason}. Insertion ignorée.")
                    result = data
                else:
                    # Aucune des conditions d'exclusion n'est remplie → Insertion
                    print(f"Le produit ID {id_produit} existe avec sources '{list(existing_sources_set)}' (pas de BO). Insertion autorisée.")
                    result = func(produits)
                    if not result:
                        id_produit_milvus = ""
                    else:
                        id_produit_milvus = result.get("ids", "")

                    output_message = {
                        "database"      : bdd,
                        "collection"    : collection,
                        "data"          : result,
                        "id_produit"    : id_produit,
                        "already_in_bdd": len(data) > 0,
                        "origin"        : origin
                    }
                    
                    data_bo_milvus.append({
                        "embedding"       : [0.0]*1024,
                        "id_produit"       : id_produit,
                        "id_produit_milvus": id_produit_milvus,
                        "date_ajout"       : datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "date_maj"         : "",
                        "origin"           : origin
                    })
            else:
                result = func(produits)
                if not result:  # None, {}, ou False
                    id_produit_milvus = ""
                else:
                    id_produit_milvus = result.get("ids", "")
                data_bo_milvus.append({
                    "embedding"       : [0.0]*1024,
                    "id_produit"       : id_produit,
                    "id_produit_milvus": id_produit_milvus,
                    "date_ajout"       : datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "date_maj"         : "",
                    "origin"           : origin
                })

            output_message = {
                "database"      : bdd,
                "collection"    : collection,
                "data"          : result,
                "id_produit"    : id_produit,
                "already_in_bdd": len(data) > 0,
                "origin"        : origin
            }
    if len(data_bo_milvus) > 0 and bdd == "milvus":
        res_correspondance = correspondance_produit.insert_correpondance_produit(data_bo_milvus)
    return output_message