from pymilvus import connections
from fastapi import APIRouter, HTTPException, Query, Path, Request
from typing import Any, Dict, Optional

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
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

# Taille maximale d'un batch Milvus (limite interne 16384)
BATCH_SIZE = 16384


@router.get("/distinct/{collection_milvus}")
async def get_distinct_values(
    request: Request,
    collection_milvus: str = Path(..., description="Nom de la collection dans Milvus"),
    distinct_field: str = Query(..., description="Nom du champ dont on veut les valeurs uniques (ex: 'url', 'domaine', 'page_type')"),
    limit: Optional[int] = Query(None, ge=1, description="Nombre max de valeurs distinctes à retourner (défaut: tout)"),
    offset: int = Query(0, ge=0, description="Nombre de valeurs distinctes à sauter (pour pagination)"),
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
• {"domaine": "hellopro.fr"} → recherche exacte <br>
• {"domaine": {"$like": "%hellopro%"}} → correspondance partielle"""),
):
    """
    Retourne les valeurs uniques (distinct) d'un champ donné dans une collection Milvus,
    avec possibilité de filtrage par un ou plusieurs champs via le paramètre metadata.

    **Cas d'usage:**
    - Liste des URLs uniques d'un domaine dans siteweb_2
    - Liste des domaines distincts dans siteweb_2
    - Liste des catégories uniques dans produits
    - Fonctionne pour n'importe quelle collection et n'importe quel champ
    """

    # --- 1. Parsing du paramètre metadata ---
    try:
        parsed_metadata = json.loads(metadata) if metadata else {}
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Paramètre 'metadata' invalide. Doit être un JSON valide.")

    collection_name = collection_milvus

    try:
        # --- 2. Connexion à Milvus ---
        _connect_to_milvus()

        # --- 3. Vérifier que la collection existe ---
        if not utility.has_collection(collection_name):
            raise HTTPException(
                status_code=404,
                detail=f"La collection '{collection_name}' n'existe pas dans Milvus."
            )

        collection = get_loaded_collection(collection_name)

        # --- 4. Validation dynamique des champs via le schéma de la collection ---
        schema_field_names = [field.name for field in collection.schema.fields]

        # Récupérer le nom du champ primary key
        primary_key_field = None
        for field in collection.schema.fields:
            if field.is_primary:
                primary_key_field = field.name
                break

        if not primary_key_field:
            raise HTTPException(
                status_code=500,
                detail=f"Impossible de déterminer la clé primaire de la collection '{collection_name}'."
            )

        # Vérifier que le champ distinct existe dans le schéma
        if distinct_field not in schema_field_names:
            raise HTTPException(
                status_code=400,
                detail=f"Le champ '{distinct_field}' n'existe pas dans la collection '{collection_name}'. "
                       f"Champs disponibles: {', '.join(schema_field_names)}"
            )

        # Vérifier que les champs de filtrage existent dans le schéma
        if parsed_metadata:
            for filter_field in parsed_metadata.keys():
                if filter_field not in schema_field_names:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Le champ de filtrage '{filter_field}' n'existe pas dans la collection '{collection_name}'. "
                               f"Champs disponibles: {', '.join(schema_field_names)}"
                    )

        # --- 5. Construction de l'expression de filtrage ---
        filter_expr = _build_metadata_expression(parsed_metadata) if parsed_metadata else ""

        # --- 6. Requête par batch avec pagination par curseur ---
        unique_values = set()
        last_pk = None
        total_rows_scanned = 0

        # Champs à récupérer : le champ distinct + la clé primaire (pour la pagination)
        output_fields = [distinct_field]
        if distinct_field != primary_key_field:
            output_fields.append(primary_key_field)

        guard = request.app.state.concurrency_guard

        while True:
            # Construire l'expression pour ce batch
            expr_parts = []
            if filter_expr:
                expr_parts.append(filter_expr)
            if last_pk is not None:
                expr_parts.append(f"{primary_key_field} > {last_pk}")

            current_expr = " and ".join(expr_parts) if expr_parts else ""

            try:
                async with guard.slot():
                    results = await asyncio.to_thread(
                        collection.query,
                        expr=current_expr,
                        output_fields=output_fields,
                        offset=0,
                        limit=BATCH_SIZE,
                    )
            except MilvusException as e:
                logger.error(f"[distinct] Erreur Milvus lors de la requête sur '{collection_name}': {e}")
                raise HTTPException(
                    status_code=500,
                    detail=f"Erreur Milvus lors de la requête: {str(e)}"
                )

            if not results:
                break

            # Accumuler les valeurs uniques
            for entity in results:
                value = entity.get(distinct_field)
                if value is not None and value != "":
                    unique_values.add(value)
                # Mettre à jour le curseur de pagination
                last_pk = entity[primary_key_field]

            total_rows_scanned += len(results)

            # Si on a reçu moins que le batch, on a tout récupéré
            if len(results) < BATCH_SIZE:
                break

        # --- 7. Trier les valeurs, paginer et construire la réponse ---
        sorted_values = sorted(unique_values, key=lambda x: str(x))
        total_distinct = len(sorted_values)

        # Appliquer offset/limit pour la pagination (si spécifiés)
        if limit is not None:
            paginated_values = sorted_values[offset:offset + limit]
        elif offset > 0:
            paginated_values = sorted_values[offset:]
        else:
            paginated_values = sorted_values

        return {
            "status": "success",
            "collection": collection_name,
            "distinct_field": distinct_field,
            "filters": parsed_metadata if parsed_metadata else None,
            "total_rows_scanned": total_rows_scanned,
            "total_distinct": total_distinct,
            "count": len(paginated_values),
            "offset": offset,
            "limit": limit,
            "values": paginated_values
        }

    except HTTPException:
        # Re-raise les HTTPException telles quelles (ne pas les wrapper dans un 500)
        raise
    except MilvusException as e:
        logger.error(f"[distinct] Erreur Milvus: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur Milvus: {str(e)}")
    except Exception as e:
        logger.error(f"[distinct] Erreur inattendue: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erreur serveur: {str(e)}")


# ============================================================
# Fonctions utilitaires (répliquées depuis read.py pour autonomie du module)
# ============================================================

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


def _connect_to_milvus():
    # connections.connect("default", uri=.config.ZILLIZ_URI, token=self.config.ZILLIZ_API_KEY)
    config = Configuration()
    connections.connect("default", host=config.ZILLIZ_URI, port=config.ZILLIZ_PORT, user=config.ZILLIZ_USER, password=config.ZILLIZ_PASSWORD)
