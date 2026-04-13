from app.schemas.check_doublon_shemas import SearchRequest
from pymilvus import connections, Collection, utility

from app.core.credentials import settings

from common_utils.database.MilvusProduitCrud import MilvusProduitsCrud
from common_utils.database.MilvusFournisseursCrud import MilvusFournisseursCrud

import logging
import requests
import httpx
from functools import lru_cache


logger = logging.getLogger(__name__)

def get_milvus_connection():
    alias = "default"
    try:
        if not connections.has_connection(alias):
            logger.info("Connexion à Milvus...")
            # connections.connect(alias, uri=settings.MILVUS_URI, token=settings.MILVUS_TOKEN)
            connections.connect(alias, host=settings.ZILLIZ_URI, port=settings.ZILLIZ_PORT, user=settings.ZILLIZ_USER, password=settings.ZILLIZ_PASSWORD)
            logger.info(f"Connecté à Milvus.")
    except Exception as e:
        logger.error(f"❌ Erreur de connexion à Milvus: {e}")
        raise e


@lru_cache(maxsize=16)
def get_collection(collection_name: str) -> Collection:
    """Return a cached Collection object for the given name."""
    return Collection(collection_name)


def get_loaded_collection(collection_name: str) -> Collection:
    """Return a Collection that is guaranteed to be loaded into Milvus memory."""
    collection = get_collection(collection_name)
    load_state = utility.load_state(collection_name)
    if str(load_state) != "Loaded":
        logger.info(f"Collection '{collection_name}' not loaded (state={load_state}), loading...")
        collection.load()
    return collection