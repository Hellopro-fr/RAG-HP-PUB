import time
from fastapi import APIRouter, HTTPException, status
from app.domain.models import (
    ComplexFilterRequest,
    FilterCaracteristiqueRequest,
    ResultProduct,
    MatchingPayload,
    MatchingPayloadIdProduit,
    MatchingResponse,
    Produit,
    CaracteristiqueMatching,
)
from app.services.recommendation_service import recommendation_service
from app.services.recommendation_service_v2 import recommendation_service_v2
import logging

router = APIRouter()


@router.post("/filter", response_model=ResultProduct, response_model_exclude_none=True)
async def complex_filter_products(request: ComplexFilterRequest):
    """
    Advanced filter: Filters products based on detailed constraints.
    Uses V4 Hybrid Logic (Inverted Index + Classic Scoring).
    """
    try:
        if not request.ids:
            return ResultProduct(data=[], info={"message": "No filters provided"})

        # We only support V4 logic in this microservice implementation
        results = await recommendation_service.get_products_by_complex_filters(request)
        return results

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An internal error occurred while filtering products: {str(e)}",
        )


@router.post(
    "/filter-by-caracteristique",
    response_model=MatchingResponse,
    response_model_exclude_none=True,
)
async def filter_by_caracteristique(request: MatchingPayload):
    """
    Filter products based on CaracteristiqueTechnique constraints.
    Uses MatchingPayload schema with MatchingOptions.Score for caracteristique weights.
    Weights are determined by poids_caracteristique ("critique" or "secondaire") mapped to options.score values.
    Returns MatchingResponse with liste_produit, top_produit, and temps_de_traitement.
    """
    try:
        if not request.liste_caracteristique:
            return MatchingResponse(
                top_produit=[],
                liste_produit=[],
                temps_de_traitement=0.0,
            )

        results = await recommendation_service.get_products_by_caracteristique_filters(
            request
        )
        return results

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An internal error occurred while filtering products: {str(e)}",
        )


@router.post(
    "/{product_id}/score",
    response_model=ResultProduct,
    response_model_exclude_none=True,
)
async def score_specific_product(product_id: str, request: ComplexFilterRequest):
    """
    Calculates the score of a specific product against the provided complex filters.
    """
    try:
        if not request.ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No filters provided for scoring.",
            )

        result = await recommendation_service.get_products_by_complex_filters(
            request, target_product_id=product_id
        )

        if not result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product '{product_id}' not found or does not match the category filter.",
            )

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An internal error occurred while scoring the product: {str(e)}",
        )


@router.post(
    "/matching",
    response_model=MatchingResponse,
    response_model_exclude_none=True,
)
async def match_products(request: MatchingPayloadIdProduit):
    """
    Endpoint pour effectuer le matching de produits.
    Recoit un contexte utilisateur et des critères, retourne une liste de produits scorés.
    Set "v": 2 in the request body to use the V2 Python-scoring pipeline.
    """
    try:
        if not request.liste_caracteristique:
            return MatchingResponse(
                top_produit=[],
                liste_produit=[],
                temps_de_traitement=0.0,
            )

        service = recommendation_service_v2 if request.v == 2 else recommendation_service

        if request.rerank.use_rerank:
            result = await service.get_products_by_caracteristique_filters_rerank(
                request
            )
        else:
            result = (
                await service.get_products_by_caracteristique_filters(
                    request
                )
            )
        return result

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An internal error occurred while filtering products: {str(e)}",
        )
