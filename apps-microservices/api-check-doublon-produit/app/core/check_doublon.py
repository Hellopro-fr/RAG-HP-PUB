from app.schemas.check_doublon_shemas import SearchRequest
from pymilvus import connections, Collection, utility

from common_utils.database.config.settings import Configuration, settings

import logging


logger = logging.getLogger(__name__)

async def search_in_milvus(request: SearchRequest):
    logger.info(f"[MILVUS] Recherche: nom_produit='{request.nom_produit}...', domaine={request.domaine[:50]}")
    
    return {
        "is_doublon": False,
        "from_similarity": False,
        "score": 0.0
    }
    

def get_milvus_connection():
    alias = "default"
    try:
        if not connections.has_connection(alias):
            logger.info("Connexion à Milvus...")
            # connections.connect(alias, uri=settings.MILVUS_URI, token=settings.MILVUS_TOKEN)
            connections.connect(alias, host=settings.ZILLIZ_URI, port=settings.ZILLIZ_PORT)
            logger.info(f"Connecté à Milvus.")
    except Exception as e:
        logger.error(f"❌ Erreur de connexion à Milvus: {e}")
        raise e