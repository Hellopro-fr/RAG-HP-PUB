from common_utils.database.QdrantWebsiteCrud import QdrantWebsiteCrud
from common_utils.database.MilvusWebsiteCrud import MilvusWebsiteCrud

from common_utils.autres.CollectionName import CollectionName
import logging

def insertion_data(website_data: dict) -> dict:
    """
    Inserts website data into the specified vector database after checking for duplicates.
    This function now raises exceptions on failure for the consumer to handle.

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

    logging.info(f"Début du traitement pour l'URL: {url}")

    try:
        collection_enum = CollectionName(collection)
    except ValueError:
        logging.error("'%s' n'est pas un nom de collection valide.", collection)
        raise ValueError(f"Nom de collection invalide: {collection}")

    # Initialisation du client de base de données
    if bdd.lower() == "milvus":
        base_vectorielle = MilvusWebsiteCrud()
    else:
        base_vectorielle = QdrantWebsiteCrud()

    # --- Étape 1: Vérifier si l'URL existe déjà ---
    try:
        res = base_vectorielle.get_website(url=url, page_type=page_type)
        status = res.get("status")
        data = res.get("data", [])

        if status == "error":
            raise Exception(f"Erreur lors de la vérification de l'existence de l'URL: {res.get('message')}")
        
        if data:
            logging.info(f"L'URL {url} existe déjà dans la base de données. Insertion ignorée.")
            return {
                "status": "skipped",
                "message": f"L'URL {url} existe déjà.",
                "url": url,
                "already_in_bdd": True
                }
    except Exception as e:
        logging.error(f"Échec de la vérification de l'URL {url}: {e}")
        raise # Propage l'exception pour que le consumer la gère (retry/DLQ)

    # --- Étape 2: Insérer les données si elles n'existent pas ---
    try:
        logging.info(f"Insertion de {len(websites)} chunk(s) pour l'URL {url} dans {bdd}...")
        func = base_vectorielle.insert_website
        result = func(websites)

        if not result or result.get("status") != "success":
            raise Exception(f"L'insertion a échoué pour l'URL {url}. Réponse de la BDD: {result}")

        logging.info(f"✓ Insertion réussie pour l'URL {url}.")
        
        return {
            "status": "success",
            "database": bdd,
            "collection": collection,
            "data": result,
            "url": url,
            "already_in_bdd": False
        }
    except Exception as e:
        logging.error(f"Échec de l'insertion pour l'URL {url}: {e}")
        raise # Propage l'exception pour que le consumer la gère (retry/DLQ)