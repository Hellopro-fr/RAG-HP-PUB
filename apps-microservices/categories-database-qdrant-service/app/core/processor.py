from common_utils.database.QdrantCategoriesCrud import QdrantCategoriesCrud
from common_utils.database.MilvusCategoriesCrud import MilvusCategoriesCrud
from common_utils.database.MilvusCategoriesInserer import MilvusCategoriesInserer

from common_utils.autres.CollectionName import CollectionName
import logging
from datetime import datetime

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
    if func and len(categories) > 0:
        id_categorie = categories[0].get('id_categorie', 'id_categorie inconnu')
        res = base_vectorielle.get_categories(id_categorie=id_categorie)
        correspondance_categories = MilvusCategoriesInserer()
        
        status = res.get("status")
        data   = res.get("data", [])
        code   = res.get("code", None)
        message = res.get("message", "")
        data_bo_milvus = []
        
        if status == "error":
            if code == 404:
                result = func(categories)
                if not result:  # None, {}, ou False
                    id_datas_milvus = ""
                else:
                    id_datas_milvus = result.get("ids", "")
                    
                output_message = {
                    "database"      : bdd,
                    "collection"    : collection,
                    "data"          : result,
                    "id_categorie"  : id_categorie,
                    "already_in_bdd": len(data) > 0
                }
                
                data_bo_milvus.append({
                    "embedding"          : [0.0]*1024,
                    "id_categorie_milvus": id_datas_milvus,
                    "id_categorie"       : id_categorie,
                    "date_ajout"         : datetime.now().isoformat(),
                    "date_maj"           : ""
                })
            else:
                logging.error("Erreur lors de la vérification de id_categorie  %s : %s", id_categorie, message)
                output_message = {
                    "database"    : bdd,
                    "collection"  : collection,
                    "data"        : [],
                    "id_categorie": id_categorie,
                    "error"       : message
                }
        elif status == "success":
            if len(data) > 0:
                logging.info("La id_categorie %s existe déjà dans la base de données. Insertion ignorée.", id_categorie)
                result = data
            else:
                logging.info("✅ Traitement réussi pour l'item '%s' - %s / %s.", id_categorie)
                result = func(categories)
                
                if not result:  # None, {}, ou False
                    id_datas_milvus = ""
                else:
                    id_datas_milvus = result.get("ids", "")
                
                data_bo_milvus.append({
                    "embedding"          : [0.0]*1024,
                    "id_categorie_milvus": id_datas_milvus,
                    "id_categorie"       : id_categorie,
                    "date_ajout"         : datetime.now().isoformat(),
                    "date_maj"           : ""
                })
                
            output_message = {
                "database"      : bdd,
                "collection"    : collection,
                "data"          : result,
                "id_categorie"  : id_categorie,
                "already_in_bdd": len(data) > 0
            }
        
        # for cat in categories:
        #     chunk        = cat.get('chunk_number', 'Numero chunk inconnu')
        #     total        = cat.get('total_chunks', 'Total chunk inconnu')
        #     logging.info("   ✅ Traitement réussi pour l'item '%s' - %s / %s.", id_categorie, chunk, total)
        #     result.append(func(cat))
            
    
        # output_message = {
        #     "collection": collection,
        #     "data"      : result,
        #     "id_categorie": id_categorie
        # }
        
        if len(data_bo_milvus) > 0 and bdd == "milvus":
            correspondance_categories.insert_correspondance_categories(data_bo_milvus)
    
        return output_message