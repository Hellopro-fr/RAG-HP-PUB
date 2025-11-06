from common_utils.database.MilvusDocumentCrud import MilvusDocumentCrud

from common_utils.autres.CollectionName import CollectionName
import logging

async def insertion_data(document_data: dict) -> dict:
    """
    Prend toutes les resultats de l'embedding puis ensuite inserer les chunk sur bdd vectoriel
    
    Retourne: Un dictionnaire prêt à être publié.
    """

    # todo rollbacker si pipeline normal
    document = document_data.get("data",{})
    documents = [document]
    collection = document_data.get("collection", CollectionName.DOCUMENT)
    bdd = "milvus" 

    try:
        collection_enum = CollectionName(collection)
    except ValueError:
        logging.error("'%s' n'est pas un nom de collection valide.", collection)
        return None

    base_vectorielle = MilvusDocumentCrud()

    processing_functions = {
        # CollectionName.DOCUMENT: base_vectorielle.insert_document
        CollectionName.DOCUMENT: base_vectorielle.update_document
    }

    func = processing_functions.get(collection_enum)
    
    result = []
    fichier_source = ""

    if func and len(documents) > 0:
        fichier_source = documents[0].get("fichier_source", "fichier source inconnu")
        res = await base_vectorielle.get_document(fichier_source=fichier_source)

        tab_data = res.get('data',[])
        if tab_data:
            text_bdd = tab_data[0].get('text','').strip()
            id_bdd         = tab_data[0].get('id')
            date_ajout_bdd = tab_data[0].get('date_ajout')
            if not text_bdd:
                # todo mise à jour de l'existant
                docs = []
                for item in documents:
                    item['id'] = id_bdd
                    item['date_ajout'] = date_ajout_bdd
                    item.pop('page_type',None)
                    docs.append(item)

                res_update = await func(docs)
                return res_update

        return
        status = res.get("status")
        data   = res.get("data", [])
        code   = res.get("code", None)
        message = res.get("message", "")

        if status == "error":
            if code == 404:
                result = await func(documents)
                output_message = {
                    "database"       : bdd,
                    "collection"     : collection,
                    "data"           : result,
                    "fichier_source" : fichier_source,
                    "already_in_bdd" : len(data) > 0
                }
            else:
                logging.error("Erreur lors de la vérification du fichie source %s : %s", fichier_source, message)
                output_message = {
                    "database"       : bdd,
                    "collection"     : collection,
                    "data"           : [],
                    "fichier_source" : fichier_source,
                    "error"          : message
                }

        elif status == "success":
            if len(data) > 0:
                logging.info("Le fichier source %s existe déjà dans la base de données. Insertion ignorée.", fichier_source)
                result = data
            else:
                result = await func(documents)

            output_message = {
                "database"       : bdd,
                "collection"     : collection,
                "data"           : result,
                "fichier_source" : fichier_source,
                "already_in_bdd" : len(data) > 0
            }

        return output_message
