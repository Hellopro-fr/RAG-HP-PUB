from fastapi import APIRouter, HTTPException, Body
from app.schemas.check_doublon_shemas import SearchRequest, SearchResponse, SearchReponse

from app.core.check_doublon import search_in_milvus

import logging

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/check-doublon" , summary="Vérifie le doublon produit dans Milvus")
async def milvus_search_endpoint(request: SearchRequest = Body(...)):
    try:
        logger.info(f"Requête reçue sur /check-doublon pour nom : {request.nom_produit}")
        if not request.nom_produit.strip():
            raise ValueError("Le nom ne peut pas être vide.")
        if not request.domaine:
            raise ValueError("Le domaine ne peut pas être vide.")
        
        results = await search_in_milvus(request)
        return SearchReponse(results=results, post=request)
    except ValueError as ve:
        logger.error(f"Erreur de validation (400): {ve}")
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Erreur interne du serveur (500): {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erreur interne du serveur: {e}")