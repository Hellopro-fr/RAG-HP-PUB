from fastapi import APIRouter, HTTPException, status
from typing import List
import logging

from app.domain.models import CaracteristiqueResponse
from app.services.product_service import product_service

router = APIRouter()


@router.get(
    "/{product_id}/caracteristiques", response_model=List[CaracteristiqueResponse]
)
async def get_product_characteristics(product_id: str):
    """
    Retrieves the list of technical characteristics for a given product ID.
    """
    try:
        results = await product_service.get_characteristics(product_id)

        if results is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product with ID '{product_id}' not found.",
            )

        return results

    except HTTPException:
        raise
    except Exception as e:
        logging.error(
            f"Error in GET /produits/{product_id}/caracteristiques: {e}", exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal error occurred while retrieving product characteristics.",
        )
