from fastapi import APIRouter, HTTPException, Query, Path
from typing import Optional
from common_utils.database.MilvusProduitCrud import MilvusProduitsCrud
import json

router = APIRouter()

@router.get("/{collection_milvus}/{id_ressource}")
async def get_ressource(
    collection_milvus: str = Path(..., description="Nom de la collection dans Milvus"),
    id_ressource: Optional[str] = Path(..., description="ID unique de la ressource"),
    metadata: Optional[str] = Query(None, description="Données additionnelles au format JSON")
):
    try:
        parsed_metadata = json.loads(metadata) if metadata else {}
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Paramètre 'metadata' invalide. Doit être un JSON valide.")
    
    # Logique pour récupérer les données depuis Milvus
    MP_Crud = MilvusProduitsCrud()
    result = MP_Crud.get_produit_rest(id_ressource, collection_milvus, parsed_metadata)
    # Exemple simplifié :
    # result = {
    #     "collection": collection_milvus,
    #     "id": id_ressource,
    #     "metadata": parsed_metadata
    # }

    return result
