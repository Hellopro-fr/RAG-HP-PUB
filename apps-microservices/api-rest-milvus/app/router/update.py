from fastapi import APIRouter, Path, Body, Query, HTTPException
from typing import Optional

router = APIRouter()

@router.put("/{collection_milvus}/{id_ressource}")
async def update_ressource(
    collection_milvus: str = Path(...),
    id_ressource: str = Path(...),
    database: Optional[str] = Query(None),
    body: dict = Body(...)
):
    try:
        # Exemple : mettre à jour une ressource dans Milvus
        return {
            "status": "updated",
            "collection": collection_milvus,
            "id": id_ressource,
            "database": database or "default",
            "updated_data": body
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
