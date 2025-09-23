from fastapi import APIRouter, Path, Body, Query, HTTPException
from typing import Optional

router = APIRouter()

@router.put("/{collection_milvus}/{id_ressource}")
async def update_ressource(
    collection_milvus: str = Path(...),
    id_ressource: str = Path(...),
    body: dict = Body(...)
):
    try:
        # Utiliser directement le nom de collection fourni (suppression de la contrainte de mapping)
        collection_name = collection_milvus

        # TODO: Implémenter la logique de mise à jour réelle dans Milvus
        # Exemple de réponse simulée pour le moment
        return {
            "status": "updated",
            "collection": collection_name,
            "id": id_ressource,
            "updated_data": body
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
