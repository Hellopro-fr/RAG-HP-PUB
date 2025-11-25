import logging
from common_utils.database.MilvusDocumentCrud import MilvusDocumentCrud
from common_utils.database.MilvusPjCrud import MilvusPjCrud

from common_utils.autres.CollectionName import CollectionName


async def insertion_data(document_data: dict) -> dict:
    """
    Prend toutes les resultats de l'embedding puis ensuite inserer les chunk sur bdd vectoriel
    
    Retourne: Un dictionnaire prêt à être publié.
    """

    # todo rollbacker si pipeline normal
    document = document_data.get("data",{})
    page_type = document_data.get("data",{}).get("page_type","")
    nb_pages = document_data.get("nb_pages","")
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

    if len(documents) > 0:
        fichier_source = documents[0].get("fichier_source", "fichier source inconnu")

        print(f"Document-database-service: page type {page_type}")

        if page_type == "autre" and False:
            res = await base_vectorielle.get_document(fichier_source=fichier_source)

            tab_data = res.get('data',[])
            if tab_data:
                print("Document-database-service: Mise à jour data")
                id_bdd         = tab_data[0].get('id')
                date_ajout_bdd = tab_data[0].get('date_ajout')
                # todo mise à jour de l'existant
                docs = []
                for doc in documents:
                    item = {}
                    item['id'] = id_bdd
                    item['date_ajout'] = date_ajout_bdd
                    item['id_demande'] = doc.get('id_demande',"")
                    item['embedding'] = [0.0]*1024
                    item['id_fournisseur'] = doc.get('id_fournisseur',"")
                    item['text'] = doc.get('text',"")
                    item['fichier_source'] = f"{doc.get('fichier_source','')} | {doc.get('page_type','')} | {nb_pages}"
                    docs.append(item)

                res = await func(docs)

                print("Res update: ", res)
                
            else:
                print("Document-database-service: Insertion data")

                documents_bis = []
                for document in documents:
                    document["embedding"] = [0.0]*1024
                    document["fichier_source"] = f"{document.get('fichier_source','')} | {document.get('page_type','')} | {nb_pages}"
                    documents_bis.append({**{k.replace("-", "_"): v for k, v in document.items() if k in ["id_demande","id_fournisseur","text","fichier_source","embedding"]}})
                res = await MilvusDocumentCrud().insert_document(documents_bis)
                print("Res insert: ", res)

            return res
        

        pj_crud = MilvusPjCrud()
        res = await pj_crud.get_pj(fichier_source=fichier_source)

        print("Document-database-service: Ajout data")


        status = res.get("status")
        data   = res.get("data", [])
        code   = res.get("code", None)
        message = res.get("message", "")


        if status == "error":
            if code == 404:
                result = await pj_crud.insert_pj(documents)
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
                result = await pj_crud.insert_pj(documents)

            output_message = {
                "database"       : bdd,
                "collection"     : collection,
                "data"           : result,
                "fichier_source" : fichier_source,
                "already_in_bdd" : len(data) > 0
            }

        return output_message
