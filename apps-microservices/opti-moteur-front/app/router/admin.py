"""Routes d'administration Typesense."""
from fastapi import APIRouter, HTTPException

from app.core.credentials import settings
from app.core.typesense_client import typesense_client

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get("/collections", summary="Liste des collections Typesense")
def list_collections():
    try:
        return typesense_client.client.collections.retrieve()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/collections/{name}", summary="Stats d'une collection")
def collection_stats(name: str):
    try:
        if not typesense_client.collection_exists(name):
            raise HTTPException(status_code=404, detail=f"Collection '{name}' not found")
        return typesense_client.collection_stats(name)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/collections/{name}", summary="Creer une collection avec schema standard")
def create_collection(name: str):
    try:
        return typesense_client.create_collection_if_missing(name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/collections/{name}", summary="Supprimer une collection (danger!)")
def delete_collection(name: str, confirm: bool = False):
    if not confirm:
        raise HTTPException(
            status_code=400,
            detail="Ajouter ?confirm=true pour confirmer la suppression",
        )
    try:
        typesense_client.client.collections[name].delete()
        return {"deleted": name}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
