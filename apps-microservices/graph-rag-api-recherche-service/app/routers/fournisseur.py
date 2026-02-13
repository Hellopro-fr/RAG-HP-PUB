from fastapi import APIRouter, HTTPException, Path, status
import logging
from typing import Optional

from app.domain.models import FournisseurGeoResponse
from app.services.fournisseur_service import fournisseur_service

router = APIRouter()


@router.get(
    "/{id_fournisseur}",
    response_model=FournisseurGeoResponse,
    description="Get the geographical coverage (Pays and Departements) for a specific supplier.",
)
async def get_fournisseur_geo_coverage(
    id_fournisseur: str = Path(..., description="The ID of the supplier")
):
    try:
        geo_coverage = await fournisseur_service.get_geo_coverage(id_fournisseur)

        if not geo_coverage:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Fournisseur with ID '{id_fournisseur}' not found.",
            )

        return geo_coverage

    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error fetching geo coverage for {id_fournisseur}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )
