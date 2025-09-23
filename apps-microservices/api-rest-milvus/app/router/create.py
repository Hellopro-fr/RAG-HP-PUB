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
        # Utiliser directement le nom de collection fourni (suppression de la contrainte de mapping)
        collection_name = collection_milvus

        # TODO: Implémenter la logique d'insertion réelle dans Milvus
        # Exemple de réponse simulée pour le moment
        return {
            "status": "created",
            "collection": collection_name,
            "data": body
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
