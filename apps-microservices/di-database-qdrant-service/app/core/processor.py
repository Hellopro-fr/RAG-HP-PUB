from common_utils.database.QdrantDevisCrud import QdrantDevisCrud
from common_utils.database.MilvusDevisCrud import MilvusDevisCrud
from common_utils.database.MilvusDevisInserer import MilvusDevisInserer

from common_utils.autres.CollectionName import CollectionName
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# Module-level singletons — persist across messages, reuse cached connections
_milvus_devis_crud = MilvusDevisCrud()
_qdrant_devis_crud = QdrantDevisCrud()
_correspondance_devis = MilvusDevisInserer()

# Initialized by main.py at startup
_concurrency_guard = None


def _do_milvus_operations(devis, bdd, collection, base_vectorielle, func):
    """Execute all Milvus/Qdrant operations for a devis insertion."""
    lead_id = devis[0].get("lead_id", "lead_id inconnu")
    res = base_vectorielle.get_devis(lead_id=lead_id)
    correspondance_devis = _correspondance_devis

    status = res.get("status")
    data = res.get("data", [])
    code = res.get("code", None)
    message = res.get("message", "")
    data_bo_milvus = []
    output_message = {}

    if status == "error":
        if code == 404:
            result = func(devis)
            if not result or result.get("status") == "error":
                raise Exception(f"L'insertion a échoué. Résultat: {result}")
            output_message = {
                "database": bdd,
                "collection": collection,
                "data": result,
                "lead_id": lead_id,
                "already_in_bdd": len(data) > 0,
            }
            data_bo_milvus.append(
                {
                    "embedding": [0.0] * 1024,
                    "id_devis_milvus": result.get("ids", ""),
                    "lead_id": lead_id,
                    "date_ajout": datetime.now().isoformat(),
                    "date_maj": "",
                }
            )

        else:
            error_message = (
                f"Erreur lors de la vérification de Lead ID {lead_id} : {message}"
            )
            logger.error(error_message)
            raise Exception(error_message)

    elif status == "success":
        if len(data) > 0:
            logger.info(
                "La lead_id %s existe déjà dans la base de données. Insertion ignorée.",
                lead_id,
            )
            result = data
        else:
            result = func(devis)
            if not result or result.get("status") == "error":
                raise Exception(f"L'insertion a échoué. Résultat: {result}")
            data_bo_milvus.append(
                {
                    "embedding": [0.0] * 1024,
                    "id_devis_milvus": result.get("ids", ""),
                    "lead_id": lead_id,
                    "date_ajout": datetime.now().isoformat(),
                    "date_maj": "",
                }
            )

        output_message = {
            "database": bdd,
            "collection": collection,
            "data": result,
            "lead_id": lead_id,
            "already_in_bdd": len(data) > 0,
        }

    if len(data_bo_milvus) > 0 and bdd == "milvus":
        res_corr = correspondance_devis.insert_correspondance_devis(data_bo_milvus)
        if not res_corr or res_corr.get("status") == "error":
            raise Exception(
                f"L'insertion de la correspondance a échoué. Résultat: {res_corr}"
            )

    return output_message


def insertion_data(devis_data: dict) -> dict:
    """
    Prend toutes les resultats de l'embedding puis ensuite inserer les chunk sur bdd vectoriel

    Retourne: Un dictionnaire prêt à être publié.
    """

    devis = devis_data.get("data", [])
    collection = devis_data.get("collection", CollectionName.DEVIS)
    bdd = devis_data.get("database", "qdrant")

    try:
        collection_enum = CollectionName(collection)
    except ValueError:
        logger.error("'%s' n'est pas un nom de collection valide.", collection)
        raise ValueError(f"'{collection}' n'est pas un nom de collection valide.")

    if bdd.lower() == "milvus":
        base_vectorielle = _milvus_devis_crud
    else:
        base_vectorielle = _qdrant_devis_crud

    processing_functions = {
        CollectionName.DEVIS: base_vectorielle.insert_devis,
    }

    func = processing_functions.get(collection_enum)

    if not func or len(devis) <= 0:
        raise ValueError(
            "Aucune donnée à insérer ou fonction de traitement non trouvée."
        )

    # Wrap all Milvus operations in concurrency guard
    if _concurrency_guard:
        with _concurrency_guard.slot():
            return _do_milvus_operations(devis, bdd, collection, base_vectorielle, func)
    return _do_milvus_operations(devis, bdd, collection, base_vectorielle, func)
