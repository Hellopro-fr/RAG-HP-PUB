from fastapi import APIRouter, HTTPException, Body
from app.schemas.search import SearchRequestWs as SearchRequest, SearchResponse, SearchReponse
from app.core.search import search_in_milvus
from app.core.recherche import search_in_milvus as search
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/search", tags=["Recherche - MILVUS"])
async def milvus_search_endpoint(request: SearchRequest = Body(...)):
    try:
        logger.info(f"Requête reçue sur /milvus/search pour les sources: {request.source}")
        if not request.prompt.strip():
            raise ValueError("Le prompt ne peut pas être vide.")
        if not request.source:
            raise ValueError("Au moins une source doit être spécifiée.")
        
        results = await search_in_milvus(request)
        return SearchReponse(results=results, post=request)
    except ValueError as ve:
        logger.error(f"Erreur de validation (400): {ve}")
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Erreur interne du serveur (500): {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erreur interne du serveur: {e}")
    
@router.post("/search/grpc", tags=["Recherche - MILVUS"])
async def milvus_search_endpoint(request: SearchRequest = Body(...)):
    try:
        logger.info(f"Requête reçue sur /milvus/search pour les sources: {request.source}")
        if not request.prompt.strip():
            raise ValueError("Le prompt ne peut pas être vide.")
        if not request.source:
            raise ValueError("Au moins une source doit être spécifiée.")
        
        results = await search(request)
        return SearchReponse(results=results, post=request)
    except ValueError as ve:
        logger.error(f"Erreur de validation (400): {ve}")
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Erreur interne du serveur (500): {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erreur interne du serveur: {e}")

# @router.post("/qdrant/search", response_model=SearchReponse, tags=["Recherche - QDRANT"])
# async def qdrant_search_endpoint(request: SearchRequest = Body(...)):
#     try:
#         logger.info(f"Requête reçue sur /qdrant/search pour les sources: {request.source}")
#         if not request.prompt.strip():
#             raise ValueError("Le prompt ne peut pas être vide.")
#         if not request.source:
#             raise ValueError("Au moins une source doit être spécifiée.")
            
#         results = await search_in_qdrant(request)
#         return SearchReponse(results=results, post=request)
#     except ValueError as ve:
#         logger.error(f"Erreur de validation (400): {ve}")
#         raise HTTPException(status_code=400, detail=str(ve))
#     except Exception as e:
#         logger.error(f"Erreur interne du serveur (500): {e}", exc_info=True)
#         raise HTTPException(status_code=500, detail=f"Erreur interne du serveur: {e}")
