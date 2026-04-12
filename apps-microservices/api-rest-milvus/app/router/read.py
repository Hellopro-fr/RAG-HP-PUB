from pymilvus import connections
from fastapi import APIRouter, HTTPException, Query, Path, Request
from typing import Any, Dict, Optional
from .mapping_rest_milvus import MILVUS_COLLECTIONS, MILVUS_COLLECTIONS_DEFAULT_FIELDS

import asyncio

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

from app.core.api_rest_milvus import get_loaded_collection

import json

router = APIRouter()

@router.get("/{collection_milvus}")
async def get_ressource(
    request: Request,
    collection_milvus: str = Path(..., description="Nom de la collection dans Milvus"),
    id_ressource: Optional[str] = Query(None, description="ID unique de la ressource"),
    metadata: Optional[str] = Query(None, description="""Filtres de recherche au format JSON.

Formats supportés: <br>
• Format simple: {"field": "value"} pour égalité <br>
• Format avec opérateurs: {"field": {"$operateur": valeur}} <br>
<br>
Opérateurs disponibles: <br>
• $gt → > (supérieur): {"price": {"$gt": 100}} <br>
• $gte → >= (supérieur ou égal): {"price": {"$gte": 100}} <br>
• $lt → < (inférieur): {"age": {"$lt": 30}} <br>
• $lte → <= (inférieur ou égal): {"age": {"$lte": 25}} <br>
• $eq → == (égal): {"status": {"$eq": "active"}} <br>
• $ne → != (différent): {"status": {"$ne": "deleted"}} <br>
• $in → in (dans la liste): {"category": {"$in": ["books", "electronics"]}} <br>
• $nin → not in (pas dans la liste): {"status": {"$nin": ["deleted", "archived"]}} <br>
• $like → like (correspondance): {"name": {"$like": "%phone%"}} <br>
<br>
Exemples: <br>
• {"id_produit": "123"} → recherche exacte <br>
• {"price": {"$gte": 50}, "category": {"$in": ["electronics"]}} → prix >= 50 ET catégorie electronics"""),
    limit: Optional[int] = Query(1000, description="Limite du nombre de résultats (max 10000)"),
    offset: Optional[int] = Query(0, description="Nombre d'éléments à ignorer (pagination)"),
    fields: Optional[str] = Query(None, description="Champs à retourner, séparés par des virgules (ex: 'id,name,type')"),
    order_by: Optional[str] = Query(None, description="Champ pour le tri (ex: 'id', 'price', 'created_at')"),
    order_direction: Optional[str] = Query("ASC", description="Direction du tri: 'ASC' (croissant) ou 'DESC' (décroissant)")
):
    try:
        parsed_metadata = json.loads(metadata) if metadata else {}
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Paramètre 'metadata' invalide. Doit être un JSON valide.")

    # Utiliser directement le nom de collection fourni (suppression de la contrainte de mapping)
    collection_name = collection_milvus

    # Parser les champs demandés
    parsed_fields = None
    if fields:
        parsed_fields = [field.strip() for field in fields.split(',') if field.strip()]

    # Validation de la direction de tri
    if order_direction and order_direction.upper() not in ["ASC", "DESC"]:
        raise HTTPException(status_code=400, detail="order_direction doit être 'ASC' ou 'DESC'")

    try:
        guard = request.app.state.concurrency_guard
        result = await get_ressource_rest(
            guard=guard,
            collection_name=collection_name,
            id_milvus=id_ressource,
            metadata=parsed_metadata,
            limit=limit,
            offset=offset,
            fields=parsed_fields,
            order_by=order_by,
            order_direction=order_direction.upper() if order_direction else "ASC"
        )

        if not result:
            raise HTTPException(status_code=404, detail="Ressource non trouvée.")

        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur serveur: {str(e)}")

def _build_metadata_expression(metadata: Dict[str, Any]) -> str:
    """
    Construit une expression de filtre Milvus à partir des métadonnées.

    Formats supportés:
    - Égalité simple: {"field": "value"} → field == "value"
    - Opérateurs: {"field": {"$gt": 10}} → field > 10
    - Opérateurs supportés: $gt (>), $gte (>=), $eq (==), $ne (!=), $lt (<), $lte (<=), $in, $nin (not in), $like
    """
    expr_parts = []

    for field_name, condition in metadata.items():
        if isinstance(condition, dict):
            # Format avec opérateurs: {"field": {"$gt": 10}}
            for operator, value in condition.items():
                expr_part = _build_single_condition(field_name, operator, value)
                if expr_part:
                    expr_parts.append(expr_part)
        else:
            # Format simple: {"field": "value"} → équivaut à {"field": {"$eq": "value"}}
            expr_part = _build_single_condition(field_name, "$eq", condition)
            if expr_part:
                expr_parts.append(expr_part)

    return " and ".join(expr_parts) if expr_parts else ""

def _build_single_condition(field_name: str, operator: str, value: Any) -> Optional[str]:
    """Construit une condition unique de filtre."""

    # Mapping des opérateurs
    operator_mapping = {
        "$gt": ">",
        "$gte": ">=",
        "$eq": "==",
        "$ne": "!=",
        "$lt": "<",
        "$lte": "<=",
        "$in": "in",
        "$nin": "not in",
        "$like": "like"
    }

    if operator not in operator_mapping:
        return None

    milvus_op = operator_mapping[operator]

    # Formatage selon le type de valeur et l'opérateur
    if operator in ["$in", "$nin"]:
        # Pour les opérateurs in/not in, la valeur doit être une liste
        if not isinstance(value, list):
            return None

        # Formater chaque élément de la liste selon son type
        formatted_values = []
        for item in value:
            if isinstance(item, str):
                formatted_values.append(f'"{item}"')
            else:
                formatted_values.append(str(item))

        value_str = f"[{', '.join(formatted_values)}]"
        return f"{field_name} {milvus_op} {value_str}"

    elif operator == "$like":
        # Pour LIKE, s'assurer que c'est une chaîne
        if not isinstance(value, str):
            return None
        return f'{field_name} {milvus_op} "{value}"'

    else:
        # Pour les autres opérateurs (>, >=, ==, !=, <, <=)
        if isinstance(value, str):
            # Cas spécial : chaîne vide "" → chercher les champs vides OU inexistants
            if value == "" and operator == "$eq":
                # Milvus : (field == "" or field == null) n'est pas supporté directement
                # On utilise seulement field == "" qui matche les chaînes vides
                # Note : Si le champ n'existe pas, il ne sera pas matché
                return f'{field_name} == ""'
            return f'{field_name} {milvus_op} "{value}"'
        else:
            return f"{field_name} {milvus_op} {value}"

async def get_ressource_rest(guard, collection_name: str, id_milvus: Optional[int] = None, metadata: Optional[Dict[str, Any]] = None, limit: int = 1000, offset: int = 0, fields: Optional[list] = None, order_by: Optional[str] = None, order_direction: str = "ASC") -> Dict[str, Any]:

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

            collection = get_loaded_collection(collection_name)

            expr_parts = []

            # Filtrage par ID (clé primaire)
            if id_milvus is not None:
                expr_parts.append(f"id == {id_milvus}")

            # Filtrage par metadata avec opérateurs logiques
            if metadata:
                metadata_expr = _build_metadata_expression(metadata)
                if metadata_expr:
                    expr_parts.append(metadata_expr)
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

            # Validation de la fenêtre de résultats Milvus (max 16384)
            # Note: Cette validation est commentée car nous gérons maintenant les gros offsets
            # if offset + limit > 16384:
            #     return {
            #         "status": "error",
            #         "message": f"La fenêtre de résultats (offset + limit) ne peut pas dépasser 16384. Valeur actuelle: {offset + limit}. Veuillez réduire l'offset ou la limite.",
            #         "code": 400
            #     }

            # Si aucun filtre fourni, récupérer tous les documents avec pagination
            if not expr_parts:
                # Déterminer les champs à retourner
                if fields:
                    output_fields = fields
                else:
                    output_fields = MILVUS_COLLECTIONS_DEFAULT_FIELDS.get(collection_name, ["*"])

                # Récupération de tous les documents avec offset et limit
                try:
                    # Construire le paramètre order_by si fourni
                    query_params = {
                        "expr": "",
                        "output_fields": output_fields,
                        "limit": limit,
                        "offset": offset
                    }
                    if order_by:
                        query_params["order_by"] = f"{order_by} {order_direction}"

                    async with guard.slot():
                        results = await asyncio.to_thread(collection.query, **query_params)
                except MilvusException as e:
                    if "invalid max query result window" in str(e):
                        return {
                            "status": "error",
                            "message": f"Erreur de pagination Milvus: La fenêtre de résultats (offset + limit = {offset + limit}) dépasse la limite maximale de 16384. Suggestion: utilisez un offset plus petit (maximum recommandé: {16384 - limit}) ou une limite plus petite.",
                            "code": 400,
                            "details": {
                                "max_window": 16384,
                                "requested_window": offset + limit,
                                "current_offset": offset,
                                "current_limit": limit,
                                "suggested_max_offset": max(0, 16384 - limit)
                            }
                        }
                    raise e

                return {
                    "status": "success",
                    "filters": {
                        "get_all": True,
                        "limit": limit,
                        "offset": offset,
                        "fields": fields or "default",
                        "order_by": order_by,
                        "order_direction": order_direction
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

            # Déterminer les champs à retourner
            if fields:
                output_fields = fields
            else:
                output_fields = MILVUS_COLLECTIONS_DEFAULT_FIELDS.get(collection_name, ["*"])

            try:
                # Construire le paramètre order_by si fourni
                query_params = {
                    "expr": expr,
                    "output_fields": output_fields,
                    "limit": limit,
                    "offset": offset
                }
                if order_by:
                    query_params["order_by"] = f"{order_by} {order_direction}"

                async with guard.slot():
                    results = await asyncio.to_thread(collection.query, **query_params)
            except MilvusException as e:
                if "invalid max query result window" in str(e):
                    return {
                        "status": "error",
                        "message": f"Erreur de pagination Milvus: La fenêtre de résultats (offset + limit = {offset + limit}) dépasse la limite maximale de 16384. Suggestion: utilisez un offset plus petit (maximum recommandé: {16384 - limit}) ou une limite plus petite.",
                        "code": 400,
                        "details": {
                            "max_window": 16384,
                            "requested_window": offset + limit,
                            "current_offset": offset,
                            "current_limit": limit,
                            "suggested_max_offset": max(0, 16384 - limit)
                        }
                    }
                raise e

            return {
                "status": "success",
                "filters": {
                    "id_milvus": id_milvus,
                    "metadata": metadata,
                    "expr" : expr,
                    "limit": limit,
                    "offset": offset,
                    "fields": fields or "default",
                    "order_by": order_by,
                    "order_direction": order_direction
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
        connections.connect("default", host=config.ZILLIZ_URI, port=config.ZILLIZ_PORT, user=config.ZILLIZ_USER, password=config.ZILLIZ_PASSWORD)