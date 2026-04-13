import logging
from common_utils.database.QdrantWebsiteCrud import QdrantWebsiteCrud
from common_utils.database.MilvusWebsiteCrud import MilvusWebsiteCrud

from common_utils.autres.CollectionName import CollectionName

logger = logging.getLogger(__name__)

# Module-level singletons — persist across messages, reuse cached connections
_milvus_website_crud = MilvusWebsiteCrud()
_qdrant_website_crud = QdrantWebsiteCrud()

# Initialized by main.py at startup
_concurrency_guard = None


def _do_milvus_operations(websites, bdd, collection, base_vectorielle, url, page_type, domaine):
    """Execute all Milvus/Qdrant operations for a website upsert."""
    # --- Étape 1: Upsert - Supprimer l'ancien contenu si existant ---
    try:
        if page_type in ["header", "footer"]:
            # Headers/Footers : supprimer par domaine + page_type
            logger.debug(f"Upsert {page_type}: Suppression des anciens chunks pour domaine '{domaine}'...")
            base_vectorielle.delete_website_by_domain_and_page_type(domaine=domaine, page_type=page_type)
        else:
            # Pages standard : supprimer par URL
            logger.debug(f"Upsert: Suppression des anciens chunks pour l'URL '{url}'...")
            base_vectorielle.delete_website_by_url(url=url)
    except Exception as e:
        logger.warning(f"Avertissement lors de la suppression pré-upsert pour '{url}': {e}. Poursuite avec l'insertion...", exc_info=True)

    # --- Étape 2: Insérer les nouvelles données ---
    try:
        logger.debug(f"Insertion de {len(websites)} chunk(s) pour l'URL {url} dans {bdd}...")
        func = base_vectorielle.insert_website
        result = func(websites)

        if not result or result.get("status") != "success":
            raise Exception(f"L'insertion a échoué pour l'URL {url}. Réponse de la BDD: {result}")

        logger.info(f"Upsert réussi pour l'URL {url}.")

        return {
            "status": "success",
            "database": bdd,
            "collection": collection,
            "data": result,
            "url": url,
            "already_in_bdd": False
        }
    except Exception as e:
        logger.error(f"Échec de l'insertion pour l'URL {url}: {e}", exc_info=True)
        raise  # Propage l'exception pour que le consumer la gère (retry/DLQ)


def insertion_data(website_data: dict) -> dict:
    """
    Inserts or updates (upserts) website data into the specified vector database.
    For pages that already exist, old chunks are deleted before inserting new ones.
    - Pages standard : suppression par URL
    - Headers/Footers : suppression par domaine + page_type
    This function raises exceptions on failure for the consumer to handle.

    Args:
        website_data (dict): The message payload containing website data.

    Returns:
        dict: A dictionary containing the result of the operation.

    Raises:
        ValueError: If the input data is invalid.
        Exception: For database-related errors during processing.
    """
    websites = website_data.get("data", [])
    collection = website_data.get("collection", CollectionName.SITEWEB)
    bdd = website_data.get("database", "qdrant")

    if not websites:
        raise ValueError("Le champ 'data' est vide ou manquant dans le message.")

    url = websites[0].get("url")
    if not url:
        raise ValueError("L'URL est manquante dans les données du site web.")

    page_type = websites[0].get("page_type")
    if not page_type:
        raise ValueError("Le type de page est manquant dans les données du site web.")

    domaine = websites[0].get("domaine")
    if not domaine:
        raise ValueError("Le domaine est manquant dans les données du site web.")

    logger.debug(f"Début du traitement pour l'URL: {url}")

    try:
        collection_enum = CollectionName(collection)
    except ValueError:
        logger.warning("'%s' n'est pas un nom de collection valide.", collection)
        raise ValueError(f"Nom de collection invalide: {collection}")

    # Initialisation du client de base de données
    if bdd.lower() == "milvus":
        base_vectorielle = _milvus_website_crud
    else:
        base_vectorielle = _qdrant_website_crud

    # Wrap all Milvus operations in concurrency guard
    if _concurrency_guard:
        with _concurrency_guard.slot():
            return _do_milvus_operations(
                websites, bdd, collection, base_vectorielle, url, page_type, domaine
            )
    return _do_milvus_operations(
        websites, bdd, collection, base_vectorielle, url, page_type, domaine
    )