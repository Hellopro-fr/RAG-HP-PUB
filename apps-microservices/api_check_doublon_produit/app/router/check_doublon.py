from fastapi import APIRouter, HTTPException, Body
from app.schemas.check_doublon_shemas import SearchRequest, SearchResponse, SearchReponse, SearchResponseLot

from typing import List

from app.core.check_doublon import search_in_milvus

import logging

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/check-doublon", response_model=SearchReponse , summary="Vérifie le doublon produit dans Milvus")
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
    
@router.post("/check-doublon-lot", summary="Vérifie le doublon pour plusieurs produits à la fois dans Milvus")
async def bulk_milvus_search_endpoint(requests: List[SearchRequest]):
    all_results = []
    
    for request in requests:
        try:
            logger.info(f"Requête en cours de traitement sur /check-doublon-lot pour nom : {request.nom_produit}")
            
            # Validation des données pour chaque élément
            if not request.nom_produit.strip():
                raise ValueError("Le nom ne peut pas être vide.")
            if not request.domaine:
                raise ValueError("Le domaine ne peut pas être vide.")
            
            # Appel de la fonction existante pour chaque requête individuelle
            results = await search_in_milvus(request)
            
            # Ajout du résultat à la liste
            all_results.append(SearchReponse(results=results, post=request))
            
        except ValueError as ve:
            logger.error(f"Erreur de validation (400) pour une des requêtes: {ve}")
            # Vous pouvez choisir de continuer même en cas d'erreur sur un des éléments
            all_results.append({
                "error": True,
                "message": str(ve),
                "post": request.dict()
            })
        except Exception as e:
            logger.error(f"Erreur interne du serveur (500) pour une des requêtes: {e}", exc_info=True)
            # Ajout d'une réponse d'erreur pour cet élément
            all_results.append({
                "error": True,
                "message": f"Erreur interne du serveur: {e}",
                "post": request.dict()
            })
            
    return all_results