from fastapi import APIRouter, Body, Path, Query, HTTPException
from typing import Optional
import json

router = APIRouter()

@router.post("/{collection_milvus}")
async def create_ressource(
    collection_milvus: str = Path(..., description="Nom de la collection dans Milvus"),
    body: dict = Body(...)
):
    try:
        # Ici tu peux appeler Milvus pour insérer les données
        # Exemple de réponse simulée
        return {
            "status": "created",
            "collection": collection_milvus,
            "database": database or "default",
            "data": body
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
