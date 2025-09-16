from fastapi import APIRouter, HTTPException, Query, Path
from typing import Optional
from .mapping_rest_milvus import MILVUS_CRUD_REGISTRY

import json

router = APIRouter()

@router.get("/{collection_milvus}")
async def get_ressource(
    collection_milvus: str = Path(..., description="Nom de la collection dans Milvus"),
    id_ressource: Optional[str] = Query(None, description="ID unique de la ressource"),
    metadata: Optional[str] = Query(None, description="Données additionnelles au format JSON")
):
    try:
        parsed_metadata = json.loads(metadata) if metadata else {}
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Paramètre 'metadata' invalide. Doit être un JSON valide.")
    
    # Obtenir la classe CRUD à partir du mapping
    crud_class = MILVUS_CRUD_REGISTRY.get(collection_milvus)
    if not crud_class:
        raise HTTPException(status_code=404, detail=f"Collection '{collection_milvus}' non supportée.")

    try:
        crud_instance = crud_class()
        result = crud_instance.get_ressource_rest(id_ressource, parsed_metadata)

        if not result:
            raise HTTPException(status_code=404, detail="Ressource non trouvée.")

        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur serveur: {str(e)}")
