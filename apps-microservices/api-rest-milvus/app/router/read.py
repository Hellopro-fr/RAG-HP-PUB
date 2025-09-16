from fastapi import APIRouter, HTTPException, Query, Path
from typing import Optional
import json

router = APIRouter()

@router.get("/{collection_milvus}/{id_ressource}")
async def get_ressource(
    collection_milvus: str = Path(..., description="Nom de la collection dans Milvus"),
    id_ressource: str = Path(..., description="ID unique de la ressource"),
    database: Optional[str] = Query(None, description="Nom de la base Milvus"),
    metadata: Optional[str] = Query(None, description="Données additionnelles au format JSON")
):
    try:
        parsed_metadata = json.loads(metadata) if metadata else {}
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Paramètre 'metadata' invalide. Doit être un JSON valide.")
    
    # Logique pour récupérer les données depuis Milvus
    # Exemple simplifié :
    result = {
        "collection": collection_milvus,
        "id": id_ressource,
        "database": database or "default",
        "metadata": parsed_metadata
    }

    return result
