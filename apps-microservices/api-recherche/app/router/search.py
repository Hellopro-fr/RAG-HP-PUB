from fastapi import APIRouter, HTTPException, Body
from app.schemas.search import SearchRequestWs as SearchRequest, SearchResponse, SearchReponse
from app.core.recherche import search_in_milvus as search
import logging
import os
from common_utils.redis.cache_service import cache_or_execute

log_format = "%(asctime)s - %(levelname)s - [WORKER_PID:%(process)d] - %(message)s"
logging.basicConfig(level=logging.INFO, format=log_format)
logger = logging.getLogger(__name__)

router = APIRouter()

async def _perform_milvus_search(request: SearchRequest):
    """
    Internal function to perform the actual Milvus search.
    """
    logger.info(f"Performing actual search for sources: {request.source}")
    return await search(request)

@router.post("/search", tags=["Recherche - MILVUS"])
async def milvus_search_endpoint(request: SearchRequest = Body(...)):
    try:
        logger.info(f"Requête reçue sur /search pour les sources: {request.source}")
        if not request.prompt.strip():
            raise ValueError("Le prompt ne peut pas être vide.")
        if not request.source:
            raise ValueError("Au moins une source doit être spécifiée.")
        
        results = await cache_or_execute(
            _perform_milvus_search,
            request,
            expire_seconds=3600  # Cache for 1 hour
        )
        return SearchReponse(results=results, post=request)
    except ValueError as ve:
        logger.error(f"Erreur de validation (400): {ve}")
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Erreur interne du serveur (500): {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erreur interne du serveur: {e}")