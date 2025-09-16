from fastapi import APIRouter, Path, Query, HTTPException
from typing import Optional

router = APIRouter()

@router.delete("/{collection_milvus}/{id_ressource}")
async def delete_ressource(
    collection_milvus: str = Path(...),
    id_ressource: str = Path(...),
    database: Optional[str] = Query(None)
):
    try:
        # Exemple : suppression dans Milvus
        return {
            "status": "deleted",
            "collection": collection_milvus,
            "id": id_ressource,
            "database": database or "default"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
