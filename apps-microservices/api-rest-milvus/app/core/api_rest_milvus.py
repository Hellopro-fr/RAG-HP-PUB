from app.schemas.check_doublon_shemas import SearchRequest
from pymilvus import connections, Collection, utility

from app.core.credentials import settings

from common_utils.database.MilvusProduitCrud import MilvusProduitsCrud
from common_utils.database.MilvusFournisseursCrud import MilvusFournisseursCrud

import logging
import requests
import httpx


logger = logging.getLogger(__name__)

def get_milvus_connection():
    alias = "default"
    try:
        if connections.has_connection(alias):
            connections.disconnect(alias)
            logger.info("Connexion existante déconnectée.")

        logger.info("Connexion à Milvus...")
        # connections.connect(alias, uri=settings.MILVUS_URI, token=settings.MILVUS_TOKEN)
        connections.connect(alias, host=settings.ZILLIZ_URI_DEV, port=settings.ZILLIZ_PORT)
        logger.info(f"Connecté à Milvus.")
    except Exception as e:
        logger.error(f"❌ Erreur de connexion à Milvus: {e}")
        raise e