from fastapi import APIRouter, HTTPException, Body
from app.schemas.check_doublon_shemas import SearchRequest, SearchResponse, SearchReponse, SearchResponseLot

from app.core.check_doublon import search_in_milvus

import logging
from typing import List

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
    all_results = []

    for request in requests:
        try:
            logger.info(f"Requête en cours de traitement sur /bulk-check-doublon pour id_produit : {request.id_produit}")

            # Validation basique
            if not request.nom_produit.strip():
                raise ValueError("Le nom ne peut pas être vide.")
            if not request.domaine:
                raise ValueError("Le domaine ne peut pas être vide.")

            # Appel de ta fonction de recherche (qui retourne un résultat formaté)
            result = await search_in_milvus(request)

            # ⚡️ Au lieu d'empiler un tableau dans un tableau, 
            # on ajoute directement le dict du produit
            all_results.append({
                "id_produit": request.id_produit,
                "is_doublon": result.is_doublon,
                "from_similarity": result.from_similarity,
                "score": result.score
            })

        except ValueError as ve:
            logger.error(f"Erreur de validation pour {request.id_produit}: {ve}")
            all_results.append({
                "id_produit": request.id_produit,
                "error": True,
                "message": str(ve),
                "is_doublon": None,
                "from_similarity": None,
                "score": None
            })

        except Exception as e:
            logger.error(f"Erreur interne pour {request.id_produit}: {e}", exc_info=True)
            all_results.append({
                "id_produit": request.id_produit,
                "error": True,
                "message": f"Erreur interne du serveur: {e}",
                "is_doublon": None,
                "from_similarity": None,
                "score": None
            })

    # Retourne une seule liste bien aplatie
    return {"results": all_results}
