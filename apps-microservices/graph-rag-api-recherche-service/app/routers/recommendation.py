from fastapi import APIRouter, HTTPException, status
from app.domain.models import ComplexFilterRequest, FilterCaracteristiqueRequest, ResultProduct
from app.services.recommendation_service import recommendation_service

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


@router.post("/filter-by-caracteristique", response_model=ResultProduct, response_model_exclude_none=True)
async def filter_by_caracteristique(request: FilterCaracteristiqueRequest):
    """
    Filter products based on CaracteristiqueTechnique constraints.
    Uses direct caracteristique matching with weights provided in request.
    Same scoring logic as /filter but keyed by caracteristique ID instead of Reponse ID.
    """
    try:
        if not request.ids:
            return ResultProduct(data=[], info={"message": "No filters provided"})

        results = await recommendation_service.get_products_by_caracteristique_filters(request)
        return results

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An internal error occurred while filtering products: {str(e)}",
        )


@router.post("/{product_id}/score", response_model=ResultProduct, response_model_exclude_none=True)
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

