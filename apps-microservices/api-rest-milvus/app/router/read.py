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

import json

router = APIRouter()

@router.get("/{collection_milvus}")
async def get_ressource(
    collection_milvus: str = Path(..., description="Nom de la collection dans Milvus"),
    id_ressource: Optional[str] = Query(None, description="ID unique de la ressource"),
    metadata: Optional[str] = Query(None, description="Données additionnelles au format JSON"),
    limit: Optional[int] = Query(1000, description="Limite du nombre de résultats (max 10000)"),
    offset: Optional[int] = Query(0, description="Nombre d'éléments à ignorer (pagination)")
):
    try:
        parsed_metadata = json.loads(metadata) if metadata else {}
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Paramètre 'metadata' invalide. Doit être un JSON valide.")
    
    # Utiliser directement le nom de collection fourni (suppression de la contrainte de mapping)
    collection_name = collection_milvus

    try:
        result = get_ressource_rest(collection_name = collection_name, id_milvus = id_ressource, metadata = parsed_metadata, limit = limit, offset = offset)

        if not result:
            raise HTTPException(status_code=404, detail="Ressource non trouvée.")

        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur serveur: {str(e)}")

def get_ressource_rest(collection_name: str, id_milvus: Optional[int] = None, metadata: Optional[Dict[str, Any]] = None, limit: int = 1000, offset: int = 0) -> Dict[str, Any]:

        print(f"get_ressource_rest - collection_name: {collection_name}, id_milvus: {id_milvus}, metadata: {metadata}")

        try:
            _connect_to_milvus()

            # Vérifier si la collection existe dans Milvus
            if not utility.has_collection(collection_name):
                return {
                    "status": "error",
                    "message": f"La collection '{collection_name}' n'existe pas dans Milvus.",
                    "code": 404
                }

            collection = Collection(collection_name)
            collection.load()

            expr_parts = []

            # Filtrage par ID (clé primaire)
            if id_milvus is not None:
                expr_parts.append(f"id == {id_milvus}")

            # Filtrage par metadata (clé=valeur)
            if metadata:
                for key, value in metadata.items():
                    if isinstance(value, str):
                        expr_parts.append(f'{key} == "{value}"')
                    else:
                        expr_parts.append(f"{key} == {value}")
            # Validations
            if limit > 10000:
                return {
                    "status": "error",
                    "message": "La limite ne peut pas dépasser 10000 résultats.",
                    "code": 400
                }

            if offset < 0:
                return {
                    "status": "error",
                    "message": "L'offset ne peut pas être négatif.",
                    "code": 400
                }

            # Si aucun filtre fourni, récupérer tous les documents avec pagination
            if not expr_parts:
                # Récupération de tous les documents avec offset et limit
                output_fields = MILVUS_COLLECTIONS_DEFAULT_FIELDS.get(collection_name, ["*"])
                results = collection.query(expr="", output_fields=output_fields, limit=limit, offset=offset)

                return {
                    "status": "success",
                    "filters": {
                        "get_all": True,
                        "limit": limit,
                        "offset": offset
                    },
                    "pagination": {
                        "current_page": (offset // limit) + 1,
                        "page_size": limit,
                        "offset": offset,
                        "returned_count": len(results)
                    },
                    "count": len(results),
                    "data": results
                }

            # Construction de l'expression finale
            expr = " and ".join(expr_parts)

            # Champs à retourner - utilise les champs par défaut du mapping s'ils existent, sinon tous les champs
            output_fields = MILVUS_COLLECTIONS_DEFAULT_FIELDS.get(collection_name, ["*"])


            results = collection.query(expr=expr, output_fields=output_fields, limit=limit, offset=offset)

            return {
                "status": "success",
                "filters": {
                    "id_milvus": id_milvus,
                    "metadata": metadata,
                    "expr" : expr,
                    "limit": limit,
                    "offset": offset
                },
                "pagination": {
                    "current_page": (offset // limit) + 1,
                    "page_size": limit,
                    "offset": offset,
                    "returned_count": len(results)
                },
                "count": len(results),
                "data": results
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