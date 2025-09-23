import json
from pymilvus import connections
from fastapi import APIRouter, HTTPException, Query, Path
from typing import Any, Dict, Optional
from .mapping_rest_milvus import MILVUS_COLLECTIONS, MILVUS_COLLECTIONS_DEFAULT_FIELDS, MILVUS_COLLECTIONS_UNIQUE_FIELD
from .read import get_ressource_rest


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
    
    # Utiliser directement le nom de collection fourni (suppression de la contrainte de mapping)
    collection_name = collection_milvus

    try:
        result = delete_ressource_rest(collection_name = collection_name, id_milvus = id_ressource, metadata = parsed_metadata)

        if not result:
            raise HTTPException(status_code=404, detail="Ressource non trouvée.")

        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur serveur: {str(e)}")

def delete_ressource_rest(collection_name: str, id_milvus: Optional[int] = None, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:

        print(f"delete_ressource_rest - collection_name: {collection_name}, id_milvus: {id_milvus}, metadata: {metadata}")

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
            values_to_delete_in_correspondance = None
            if collection_name in MILVUS_COLLECTIONS_UNIQUE_FIELD:
                existings = get_ressource_rest(collection_name, id_milvus, metadata)
                unique_field = MILVUS_COLLECTIONS_UNIQUE_FIELD.get(collection_name)
                values_to_delete_in_correspondance = list({doc.get(unique_field) for doc in existings.get("data", [])})


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
            # Aucun filtre fourni ?
            if not expr_parts:
                return {
                    "status": "error",
                    "message": "Aucun critère de recherche fourni (id_milvus ou metadata).",
                    "code": 400
                }

            # Construction de l'expression finale
            expr = " and ".join(expr_parts)

            # Champs à retourner (tu peux les adapter)
            # output_fields = MILVUS_COLLECTIONS_DEFAULT_FIELDS.get(collection_name, ["*"])
            if expr_parts:
                results = collection.delete(expr=expr)

            if values_to_delete_in_correspondance is not None:

                # collection_correspondance_name = 
                collection_correspondance = Collection("correspondance_" + collection_name + "_bo_milvus")
                collection_correspondance.load()
                values_to_delete_in_correspondance = [doc.get(unique_field) for doc in existings.get("data", [])]

                # Ensure they are strings for Milvus expr
                string_values = [f'"{v}"' for v in values_to_delete_in_correspondance]
                expr = f'{unique_field} in [{", ".join(string_values)}]'

                if string_values:
                    res = collection_correspondance.delete(expr=expr)
                    # print(f"Suppression dans la collection de correspondance avec l'expression: {expr} - {collection_correspondance_name}")

            return {
                "status": "success",
                "filters": {
                    "id_milvus": id_milvus,
                    "metadata": metadata,
                    "expr" : expr
                },
                "data": {
                    "delete_count": results.delete_count,
                    "primary_keys": list(results.primary_keys) if results.primary_keys else []
                },
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