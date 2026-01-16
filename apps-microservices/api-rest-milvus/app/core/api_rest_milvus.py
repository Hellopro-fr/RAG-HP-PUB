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
        if not connections.has_connection(alias):
            logger.info("Connexion à Milvus...")
            # connections.connect(alias, uri=settings.MILVUS_URI, token=settings.MILVUS_TOKEN)
            connections.connect(alias, host=settings.ZILLIZ_URI, port=settings.ZILLIZ_PORT, user=settings.ZILLIZ_USER, password=settings.ZILLIZ_PASSWORD)
            logger.info(f"Connecté à Milvus.")
    except Exception as e:
        logger.error(f"❌ Erreur de connexion à Milvus: {e}")
        raise e