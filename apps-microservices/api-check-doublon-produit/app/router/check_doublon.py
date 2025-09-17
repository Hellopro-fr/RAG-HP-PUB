from fastapi import APIRouter, HTTPException, Body
from app.schemas.check_doublon_shemas import SearchRequest, SearchResponse, SearchReponse, SearchResponseLot

from app.core.check_doublon import search_in_milvus

import logging
from typing import List

import asyncio

router = APIRouter()
logger = logging.getLogger(__name__)

def validate_request(req: SearchRequest):
    if not req.nom_produit or not req.nom_produit.strip():
        raise ValueError("Le nom ne peut pas être vide.")
    if not req.domaine:
        raise ValueError("Le domaine ne peut pas être vide.")

@router.post("/check-doublon", response_model=SearchReponse , summary="Vérifie le doublon produit dans Milvus")
async def milvus_search_endpoint(request: SearchRequest = Body(...)):
    try:
        logger.info(f"Requête reçue sur /check-doublon pour nom : {request.nom_produit}")
        validate_request(request)
        
        results = await search_in_milvus(request)
        return SearchReponse(result = results)
    except ValueError as ve:
        logger.error(f"Erreur de validation (400): {ve}")
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Erreur interne du serveur (500): {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erreur interne du serveur: {e}")

# Nouveau point de terminaison pour les requêtes multiples
@router.post("/check-doublon-lot", summary="Vérifie le doublon pour plusieurs produits à la fois dans Milvus")
async def bulk_milvus_search_endpoint(requests: List[SearchRequest]):
    tasks = []
    for req in requests:
        try:
            validate_request(req)
            tasks.append(search_in_milvus(req))
        except Exception as e:
            logger.error(f"Erreur validation pour {req.id_produit}: {e}")
            tasks.append(e)  # On met directement une erreur
    
    raw_results = await asyncio.gather(*[t if not isinstance(t, Exception) else asyncio.sleep(0, result=t) for t in tasks], return_exceptions=True)
    
    all_results = []
    for req, res in zip(requests, raw_results):
        if isinstance(res, Exception):
            logger.error(f"Erreur interne pour {req.id_produit}: {res}", exc_info=True)
            all_results.append(SearchResponse(
                etat            = "ERROR",
                is_doublon      = False,
                from_similarity = False,
                score           = 0.0,
                error           = str(res),
                id_produit      = req.id_produit,
            ))
        else:
            all_results.append(SearchResponse(
                etat            = "SUCCESS",
                is_doublon      = res.get("is_doublon", False),
                from_similarity = res.get("from_similarity", False),
                score           = res.get("score", 0.0),
                id_produit      = req.id_produit,
            ))

    return SearchResponseLot(results=all_results)
