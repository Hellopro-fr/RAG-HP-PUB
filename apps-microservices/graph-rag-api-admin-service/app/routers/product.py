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


@router.delete(
    "/{product_id}",
    response_model=dict,
    status_code=status.HTTP_200_OK,
    summary="Delete a product",
    description="Deletes a product by its ID and returns the backup data (properties of the deleted node).",
)
async def delete_product(product_id: str):
    """
    Deletes a product and returns its data for backup purposes.
    """
    try:
        backup_data = await product_service.delete_produit(product_id)

        if backup_data is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product with ID '{product_id}' not found.",
            )

        return backup_data

    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error in DELETE /produits/{product_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal error occurred while deleting the product.",
        )
