from app.schemas.check_doublon_shemas import SearchRequest
import logging


logger = logging.getLogger(__name__)

async def search_in_milvus(request: SearchRequest):
    logger.info(f"[MILVUS] Recherche: nom_produit='{request.nom_produit}...', domaine={request.domaine[:50]}")
    
    return {
        "is_doublon": False,
        "from_similarity": False,
        "score": 0.0
    }