import logging
from common_utils.database.MilvusDocumentCrud import MilvusDocumentCrud
from common_utils.database.MilvusPjCrud import MilvusPjCrud

from common_utils.autres.CollectionName import CollectionName

logger = logging.getLogger(__name__)

# Module-level singletons — persist across messages, reuse cached connections
base_vectorielle = MilvusDocumentCrud()
pj_crud = MilvusPjCrud()


async def insertion_data(document_data: dict) -> dict:
    """
    Prend toutes les resultats de l'embedding puis ensuite inserer les chunk sur bdd vectoriel

    Retourne: Un dictionnaire prêt à être publié.
    """
    documents = document_data.get("data", [])

    if isinstance(documents, list):
        page_type = documents[0].get("page_type", "")
    else:
        document = document_data.get("data", {})
        page_type = document.get("page_type", "")
        documents = [document]

    nb_pages = document_data.get("nb_pages", "")
    collection = document_data.get("collection", CollectionName.DOCUMENT)
    bdd = "milvus"

    try:
        collection_enum = CollectionName(collection)
    except ValueError:
        logger.error("'%s' n'est pas un nom de collection valide.", collection)
        return None

    processing_functions = {
        # CollectionName.DOCUMENT: base_vectorielle.insert_document
        CollectionName.DOCUMENT: base_vectorielle.update_document
    }

    func = processing_functions.get(collection_enum)

    result = []
    fichier_source = ""

    if len(documents) > 0:
        fichier_source = documents[0].get("fichier_source", "fichier source inconnu")

        if page_type == "autre":
            res = await base_vectorielle.get_document(fichier_source=fichier_source)

            tab_data = res.get("data", [])
            if tab_data:
                id_bdd = tab_data[0].get("id")
                date_ajout_bdd = tab_data[0].get("date_ajout")
                # todo mise à jour de l'existant
                docs = []
                for doc in documents:
                    item = {}
                    item["id"] = id_bdd
                    item["date_ajout"] = date_ajout_bdd
                    item["id_demande"] = doc.get("id_demande", "")
                    item["embedding"] = [0.0] * 1024
                    item["id_fournisseur"] = doc.get("id_fournisseur", "")
                    item["text"] = doc.get("text", "")
                    item["fichier_source"] = (
                        f"{doc.get('fichier_source','')} | {doc.get('page_type','')} | {nb_pages}"
                    )
                    docs.append(item)

                res = await func(docs)
                if not res or res.get("status") == "error":
                    raise Exception(f"L'update a échoué. Résultat: {res}")

                logger.debug("Res update: %s", res)

            else:
                documents_bis = []
                for document in documents:
                    document["embedding"] = [0.0] * 1024
                    document["fichier_source"] = (
                        f"{document.get('fichier_source','')} | {document.get('page_type','')} | {nb_pages}"
                    )
                    documents_bis.append(
                        {
                            **{
                                k.replace("-", "_"): v
                                for k, v in document.items()
                                if k
                                in [
                                    "id_demande",
                                    "id_fournisseur",
                                    "text",
                                    "fichier_source",
                                    "embedding",
                                ]
                            }
                        }
                    )
                res = await base_vectorielle.insert_document(documents_bis)
                if not res or res.get("status") == "error":
                    raise Exception(f"L'insertion a échoué. Résultat: {res}")
                logger.debug("Res insert: %s", res)

            return res

        res = await pj_crud.get_pj(fichier_source=fichier_source)

        logger.debug("Document-database-service: Ajout data")
        status = res.get("status")
        data = res.get("data", [])
        code = res.get("code", None)
        message = res.get("message", "")

        if status == "error":
            if code == 404:
                result = await pj_crud.insert_pj(documents)
                if not result or result.get("status") == "error":
                    raise Exception(
                        f"L'insertion de la PJ a échoué. Résultat: {result}"
                    )
                output_message = {
                    "database": bdd,
                    "collection": collection,
                    "data": result,
                    "fichier_source": fichier_source,
                    "already_in_bdd": len(data) > 0,
                }
            else:
                logger.error(
                    "Erreur lors de la vérification du fichier source %s : %s",
                    fichier_source,
                    message,
                )
                raise Exception(message)

        elif status == "success":
            if len(data) > 0:
                logger.info(
                    "Le fichier source %s existe déjà dans la base de données. Insertion ignorée.",
                    fichier_source,
                )
                result = data
            else:
                result = await pj_crud.insert_pj(documents)
                if not result or result.get("status") == "error":
                    raise Exception(
                        f"L'insertion de la PJ a échoué. Résultat: {result}"
                    )

            output_message = {
                "database": bdd,
                "collection": collection,
                "data": result,
                "fichier_source": fichier_source,
                "already_in_bdd": len(data) > 0,
            }

        return output_message
