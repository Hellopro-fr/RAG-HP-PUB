from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from typing import Any, Dict, Optional, List
from .read import get_ressource_rest

router = APIRouter()


class SearchRequest(BaseModel):
    """Modèle de requête pour la recherche POST - contourne l'erreur HTTP 414"""
    collection_milvus: str = Field(..., description="Nom de la collection dans Milvus")
    id_ressource: Optional[str] = Field(None, description="ID unique de la ressource")
    metadata: Optional[Dict[str, Any]] = Field(None, description="""Filtres de recherche.

Formats supportés:
• Format simple: {"field": "value"} pour égalité
• Format avec opérateurs: {"field": {"$operateur": valeur}}

Opérateurs disponibles:
• $gt → > (supérieur): {"price": {"$gt": 100}}
• $gte → >= (supérieur ou égal): {"price": {"$gte": 100}}
• $lt → < (inférieur): {"age": {"$lt": 30}}
• $lte → <= (inférieur ou égal): {"age": {"$lte": 25}}
• $eq → == (égal): {"status": {"$eq": "active"}}
• $ne → != (différent): {"status": {"$ne": "deleted"}}
• $in → in (dans la liste): {"category": {"$in": ["books", "electronics"]}}
• $nin → not in (pas dans la liste): {"status": {"$nin": ["deleted", "archived"]}}
• $like → like (correspondance): {"name": {"$like": "%phone%"}}

Exemples:
• {"id_produit": "123"} → recherche exacte
• {"price": {"$gte": 50}, "category": {"$in": ["electronics"]}} → prix >= 50 ET catégorie electronics""")
    limit: Optional[int] = Field(1000, description="Limite du nombre de résultats (max 10000)")
    offset: Optional[int] = Field(0, description="Nombre d'éléments à ignorer (pagination)")
    fields: Optional[List[str]] = Field(None, description="Liste des champs à retourner (ex: ['id', 'name', 'type'])")
    order_by: Optional[str] = Field(None, description="Champ pour le tri (ex: 'id', 'price', 'created_at')")
    order_direction: Optional[str] = Field("ASC", description="Direction du tri: 'ASC' (croissant) ou 'DESC' (décroissant)")

    class Config:
        json_schema_extra = {
            "example": {
                "collection_milvus": "produits",
                "metadata": {
                    "id_produit": {"$in": ["123", "456", "789"]},
                    "price": {"$gte": 50}
                },
                "limit": 100,
                "offset": 0,
                "fields": ["id", "id_produit", "name", "price"],
                "order_by": "price",
                "order_direction": "DESC"
            }
        }


@router.post("/search")
async def search_ressources(http_request: Request, request: SearchRequest):
    """
    Endpoint POST pour rechercher des ressources dans Milvus.

    Cette méthode POST accepte les paramètres dans le body JSON au lieu de l'URL,
    ce qui permet de contourner l'erreur HTTP 414 (Request-URI Too Large) causée
    par des URLs trop longues avec de nombreux filtres.

    Utilisez cet endpoint à la place de GET /{collection_milvus} lorsque vous avez
    beaucoup de filtres ou des listes d'IDs très longues.
    """

    # Validation de la direction de tri
    if request.order_direction and request.order_direction.upper() not in ["ASC", "DESC"]:
        raise HTTPException(status_code=400, detail="order_direction doit être 'ASC' ou 'DESC'")

    try:
        guard = http_request.app.state.concurrency_guard
        result = await get_ressource_rest(
            guard=guard,
            collection_name=request.collection_milvus,
            id_milvus=request.id_ressource,
            metadata=request.metadata,
            limit=request.limit,
            offset=request.offset,
            fields=request.fields,
            order_by=request.order_by,
            order_direction=request.order_direction.upper() if request.order_direction else "ASC"
        )

        if not result:
            raise HTTPException(status_code=404, detail="Ressource non trouvée.")

        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur serveur: {str(e)}")
