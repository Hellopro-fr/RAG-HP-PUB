from common_utils.database.QdrantEchangeCrud import QdrantEchangeCrud
from common_utils.database.MilvusEchangeCrud import MilvusEchangeCrud
from common_utils.database.MilvusEchangeInserer import MilvusEchangeInserer

from common_utils.autres.CollectionName import CollectionName
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# Module-level singletons — persist across messages, reuse cached connections
_milvus_echange_crud = MilvusEchangeCrud()
_qdrant_echange_crud = QdrantEchangeCrud()
_correspondance_echange = MilvusEchangeInserer()

# Initialized by main.py at startup
_concurrency_guard = None


def _do_milvus_operations(echanges, bdd, collection, base_vectorielle, func):
    """Execute all Milvus/Qdrant operations for an echange insertion."""
    conversation_id = echanges[0].get("conversation_id", "conversation_id inconnu")
    res = base_vectorielle.get_echange(conversation_id=conversation_id)
    correspondance_echange = _correspondance_echange

    status = res.get("status")
    data = res.get("data", [])
    code = res.get("code", None)
    message = res.get("message", "")
    data_bo_milvus = []
    output_message = {}

    if status == "error":
        if code == 404:
            result = func(echanges)
            if not result or result.get("status") == "error":
                raise Exception(f"L'insertion a échoué. Résultat: {result}")
            output_message = {
                "database": bdd,
                "collection": collection,
                "data": result,
                "conversation_id": conversation_id,
                "already_in_bdd": len(data) > 0,
            }
            data_bo_milvus.append(
                {
                    "embedding": [0.0] * 1024,
                    "id_echange_milvus": result.get("ids", ""),
                    "conversation_id": conversation_id,
                    "date_ajout": datetime.now().isoformat(),
                    "date_maj": "",
                }
            )

        else:
            error_message = f"Erreur lors de la vérification de conversation ID {conversation_id} : {message}"
            logger.error(error_message)
            raise Exception(error_message)

    elif status == "success":
        if len(data) > 0:
            # Conversation existe déjà → MISE À JOUR
            logger.info(
                "La conversation_id %s existe déjà. Mise à jour en cours...",
                conversation_id,
            )

            if bdd.lower() == "milvus":
                # Appeler la méthode update_echange qui gère toute la logique
                result = base_vectorielle.update_echange(
                    echanges, conversation_id, correspondance_echange
                )

                if not result or result.get("status") == "error":
                    error_message = f"Erreur mise à jour pour {conversation_id}: {result.get('message') if result else 'None'}"
                    logger.error(error_message)
                    raise Exception(error_message)

                output_message = {
                    "database": bdd,
                    "collection": collection,
                    "data": result.get("data"),
                    "conversation_id": conversation_id,
                    "already_in_bdd": result.get("already_in_bdd", True),
                    "updated": result.get("updated", True),
                }
            else:
                # Pour Qdrant, garder l'ancien comportement (skip)
                logger.info(
                    "La conversation_id %s existe déjà dans la base de données. Insertion ignorée.",
                    conversation_id,
                )
                result = data
                output_message = {
                    "database": bdd,
                    "collection": collection,
                    "data": result,
                    "conversation_id": conversation_id,
                    "already_in_bdd": True,
                }
        else:
            # Conversation n'existe pas → INSERTION NORMALE
            result = func(echanges)
            if not result or result.get("status") == "error":
                raise Exception(f"L'insertion a échoué. Résultat: {result}")
            data_bo_milvus.append(
                {
                    "embedding": [0.0] * 1024,
                    "id_echange_milvus": result.get("ids", ""),
                    "conversation_id": conversation_id,
                    "date_ajout": datetime.now().isoformat(),
                    "date_maj": "",
                }
            )

            output_message = {
                "database": bdd,
                "collection": collection,
                "data": result,
                "conversation_id": conversation_id,
                "already_in_bdd": False,
            }

    if len(data_bo_milvus) > 0 and bdd.lower() == "milvus":
        res_corr = correspondance_echange.insert_correspondance_echange(data_bo_milvus)
        if not res_corr or res_corr.get("status") == "error":
            raise Exception(
                f"L'insertion de la correspondance a échoué. Résultat: {res_corr}"
            )

    return output_message


def insertion_data(echange_data: dict) -> dict:
    """
    Prend toutes les resultats de l'embedding puis ensuite inserer les chunk sur bdd vectoriel

    Retourne: Un dictionnaire prêt à être publié.
    """

    echanges = echange_data.get("data", [])
    collection = echange_data.get("collection", CollectionName.ECHANGE)
    bdd = echange_data.get("database", "qdrant")

    try:
        collection_enum = CollectionName(collection)
    except ValueError:
        logger.error("'%s' n'est pas un nom de collection valide.", collection)
        raise ValueError(f"'{collection}' n'est pas un nom de collection valide.")

    if bdd.lower() == "milvus":
        base_vectorielle = _milvus_echange_crud
    else:
        base_vectorielle = _qdrant_echange_crud

    processing_functions = {
        CollectionName.ECHANGE: base_vectorielle.insert_echange,
    }

    func = processing_functions.get(collection_enum)

    if not func or len(echanges) <= 0:
        raise ValueError(
            "Aucune donnée d'échange fournie ou fonction de traitement invalide."
        )

    # Wrap all Milvus operations in concurrency guard
    if _concurrency_guard:
        with _concurrency_guard.slot():
            return _do_milvus_operations(echanges, bdd, collection, base_vectorielle, func)
    return _do_milvus_operations(echanges, bdd, collection, base_vectorielle, func)
