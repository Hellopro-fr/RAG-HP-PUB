import json
from pymilvus import connections
from fastapi import APIRouter, HTTPException, Query, Path
from typing import Any, Dict, Optional
from .mapping_rest_milvus import MILVUS_COLLECTIONS, MILVUS_COLLECTIONS_DEFAULT_FIELDS


from common_utils.database.config.settings import Configuration
from common_utils.database.Utils import Utils

from pymilvus import (
    connections,
    utility,
    FieldSchema,
    CollectionSchema,
    DataType,
    Collection,
    MilvusException
)

router = APIRouter()

@router.delete("/{collection_milvus}")
async def delete_ressource(
    collection_milvus: str = Path(..., description="Nom de la collection dans Milvus"),
    id_ressource: Optional[str] = Query(None, description="ID unique de la ressource"),
    metadata: Optional[str] = Query(None, description="Données additionnelles au format JSON")
):
    try:
        parsed_metadata = json.loads(metadata) if metadata else {}
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Paramètre 'metadata' invalide. Doit être un JSON valide.")
    
    # Obtenir la classe CRUD à partir du mapping
    collection_name = MILVUS_COLLECTIONS.get(collection_milvus)



    if not collection_name:
        raise HTTPException(status_code=404, detail=f"Collection '{collection_milvus}' non supportée.")

    try:
        result = delete_ressource_rest(collection_name = collection_name, id_produit_milvus = id_ressource, metadata = parsed_metadata)

        if not result:
            raise HTTPException(status_code=404, detail="Ressource non trouvée.")

        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur serveur: {str(e)}")

def delete_ressource_rest(collection_name: str, id_produit_milvus: Optional[int] = None, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:

        print(f"delete_ressource_rest - collection_name: {collection_name}, id_produit_milvus: {id_produit_milvus}, metadata: {metadata}")

        try:
            _connect_to_milvus()
            
            collection = Collection(collection_name)
            collection.load()

            expr_parts = []

            # Filtrage par ID (clé primaire)
            if id_produit_milvus is not None:
                expr_parts.append(f"id == {id_produit_milvus}")

            # Filtrage par metadata (clé=valeur)
            if metadata:
                for key, value in metadata.items():
                    if isinstance(value, str):
                        expr_parts.append(f'{key} == "{value}"')
                    else:
                        expr_parts.append(f"{key} == {value}")
            # Aucun filtre fourni ?
            if not expr_parts:
                return {
                    "status": "error",
                    "message": "Aucun critère de recherche fourni (id_produit_milvus ou metadata).",
                    "code": 400
                }

            # Construction de l'expression finale
            expr = " and ".join(expr_parts)

            # Champs à retourner (tu peux les adapter)
            # output_fields = MILVUS_COLLECTIONS_DEFAULT_FIELDS.get(collection_name, ["*"])


            results = collection.delete(expr=expr)

            return {
                "status": "success",
                "filters": {
                    "id_produit_milvus": id_produit_milvus,
                    "metadata": metadata,
                    "expr" : expr
                },
                "data": "results"
            }

        except MilvusException as e:
            return {
                "status": "error",
                "message": str(e),
                "code": 500
            }

        except Exception as e:
            return {
                "status": "error",
                "message": str(e),
                "code": 500
            }
        
def _connect_to_milvus():
        # connections.connect("default", uri=.config.ZILLIZ_URI, token=self.config.ZILLIZ_API_KEY)
        config = Configuration()
        connections.connect("default", host=config.ZILLIZ_URI, port=config.ZILLIZ_PORT)