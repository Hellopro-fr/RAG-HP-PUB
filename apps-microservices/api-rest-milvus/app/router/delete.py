import json
from pymilvus import connections
from fastapi import APIRouter, HTTPException, Body, Path
from typing import Any, Dict, List, Union, Optional
from .mapping_rest_milvus import MILVUS_COLLECTIONS_CASCADE_MAPPING

from common_utils.database.config.settings import Configuration

from pymilvus import (
    connections,
    utility,
    Collection,
    MilvusException
)

router = APIRouter()


class CascadeConfig:
    """Modèle pour la configuration de suppression en cascade."""
    def __init__(self, enabled: bool = False, filters: Optional[Dict[str, Any]] = None):
        self.enabled = enabled
        self.filters = filters or {}

@router.delete("/{collection_milvus}")
async def delete_ressource(
    collection_milvus: str = Path(..., description="Nom de la collection dans Milvus"),
    body: Dict[str, Any] = Body(..., description="Critères de suppression", examples={
        "by_single_id": {
            "summary": "Suppression par ID unique",
            "value": {
                "ids": 123456789
            }
        },
        "by_multiple_ids": {
            "summary": "Suppression par liste d'IDs",
            "value": {
                "ids": [123456789, 987654321, 456789123]
            }
        },
        "by_filters": {
            "summary": "Suppression par filtres sur champs",
            "value": {
                "filters": {
                    "id_produit": "PROD123",
                    "source": "BO"
                }
            }
        },
        "by_filters_with_operators": {
            "summary": "Suppression par filtres avec opérateurs",
            "value": {
                "filters": {
                    "price": {"$lt": 10},
                    "status": {"$in": ["cancelled", "expired"]}
                }
            }
        },
        "with_cascade_same_filters": {
            "summary": "Suppression avec cascade (mêmes filtres)",
            "value": {
                "filters": {
                    "id_produit": "PROD123",
                    "source": "BO"
                },
                "cascade": {
                    "enabled": True
                }
            }
        },
        "with_cascade_different_filters": {
            "summary": "Suppression avec cascade (filtres différents)",
            "value": {
                "filters": {
                    "id_produit": "PROD123",
                    "source": "BO"
                },
                "cascade": {
                    "enabled": True,
                    "filters": {
                        "id_produit": "PROD123",
                        "origin": "bo"
                    }
                }
            }
        },
        "combined_with_cascade": {
            "summary": "IDs + filtres + cascade",
            "value": {
                "ids": [123, 456],
                "filters": {
                    "status": "active"
                },
                "cascade": {
                    "enabled": True,
                    "filters": {
                        "status": "active"
                    }
                }
            }
        }
    })
):
    """
    Supprime une ou plusieurs ressources dans une collection Milvus.

    **Modes de suppression :**
    - **Par ID(s)** : `{"ids": 123}` ou `{"ids": [123, 456, 789]}`
    - **Par filtres** : `{"filters": {"champ": "valeur"}}`
    - **Combiné** : `{"ids": [123, 456], "filters": {"status": "active"}}`

    **Suppression en cascade (optionnelle) :**
    - **Désactivée par défaut** : `{"cascade": {"enabled": false}}`
    - **Avec mêmes filtres** : `{"filters": {...}, "cascade": {"enabled": true}}`
    - **Avec filtres différents** : `{"cascade": {"enabled": true, "filters": {...}}}`

    **Opérateurs supportés dans filters :**
    - `$gt`, `$gte`, `$lt`, `$lte` : comparaisons
    - `$eq`, `$ne` : égalité/différence
    - `$in`, `$nin` : appartenance à une liste
    - `$like` : correspondance de pattern

    **Exemples de filtres :**
    - `{"id_produit": "PROD123"}` → égalité simple
    - `{"price": {"$gte": 50}}` → prix >= 50
    - `{"status": {"$in": ["cancelled", "expired"]}}` → status dans la liste

    **Collections supportant la cascade :**
    - produits, produits_2, produits_3, devis, categories, echanges
    """
    collection_name = collection_milvus

    # Extraire les paramètres
    ids = body.get("ids")
    filters = body.get("filters")
    cascade_data = body.get("cascade", {})

    # Parser la configuration cascade
    cascade_enabled = cascade_data.get("enabled", False)
    cascade_filters = cascade_data.get("filters")

    # Validation : au moins un critère doit être fourni
    if ids is None and not filters:
        raise HTTPException(
            status_code=400,
            detail="Au moins un critère de suppression doit être fourni : 'ids' ou 'filters'"
        )

    # Validation : liste vide
    if ids is not None and isinstance(ids, list) and len(ids) == 0:
        raise HTTPException(
            status_code=400,
            detail="La liste d'IDs ne peut pas être vide"
        )

    # Validation : filters vide
    if filters is not None and isinstance(filters, dict) and len(filters) == 0:
        filters = None

    # Re-validation après nettoyage
    if ids is None and not filters:
        raise HTTPException(
            status_code=400,
            detail="Au moins un critère de suppression valide doit être fourni"
        )

    # Validation cascade : si enabled=true, doit avoir des filtres (cascade ou principal)
    if cascade_enabled:
        # Cas bloquant : cascade activée mais aucun filtre disponible
        if not cascade_filters and not filters:
            raise HTTPException(
                status_code=400,
                detail="Cascade activée mais aucun filtre fourni. Vous devez fournir 'cascade.filters' ou 'filters'"
            )

        # Cas bloquant : seulement IDs sans filters, et pas de cascade.filters
        if ids is not None and not filters and not cascade_filters:
            raise HTTPException(
                status_code=400,
                detail="Cascade activée avec seulement des IDs. Vous devez fournir 'cascade.filters' pour la suppression en cascade"
            )

    try:
        result = delete_ressource_rest(
            collection_name=collection_name,
            ids=ids,
            filters=filters,
            cascade_enabled=cascade_enabled,
            cascade_filters=cascade_filters
        )

        if result.get("status") == "error":
            status_code = result.get("code", 500)
            raise HTTPException(status_code=status_code, detail=result.get("message"))

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur serveur: {str(e)}")

def delete_ressource_rest(
    collection_name: str,
    ids: Optional[Union[int, List[int]]] = None,
    filters: Optional[Dict[str, Any]] = None,
    cascade_enabled: bool = False,
    cascade_filters: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Supprime une ou plusieurs ressources dans une collection Milvus.

    Args:
        collection_name: Nom de la collection Milvus
        ids: ID unique (int), liste d'IDs (List[int]), ou None
        filters: Dictionnaire de filtres avec opérateurs optionnels
        cascade_enabled: Active/désactive la suppression en cascade
        cascade_filters: Filtres spécifiques pour la cascade (optionnel)

    Returns:
        Dict contenant le statut, les filtres utilisés et les résultats de suppression
    """
    print(f"delete_ressource_rest - collection: {collection_name}, ids: {ids}, filters: {filters}, cascade_enabled: {cascade_enabled}")

    try:
        # Connexion à Milvus
        _connect_to_milvus()

        # Vérifier si la collection existe
        if not utility.has_collection(collection_name):
            return {
                "status": "error",
                "message": f"La collection '{collection_name}' n'existe pas dans Milvus.",
                "code": 404
            }

        # Charger la collection
        collection = Collection(collection_name)
        collection.load()

        # Construction de l'expression de filtre pour la collection principale
        expr_parts = []

        # 1. Filtrage par IDs
        if ids is not None:
            ids_list = [ids] if isinstance(ids, int) else ids

            if len(ids_list) == 1:
                expr_parts.append(f"id == {ids_list[0]}")
            else:
                expr_parts.append(f"id in {ids_list}")

        # 2. Filtrage par autres champs
        if filters:
            filters_expr = _build_filters_expression(filters)
            if filters_expr:
                expr_parts.append(filters_expr)
            else:
                return {
                    "status": "error",
                    "message": "Les filtres fournis n'ont généré aucune expression valide.",
                    "code": 400
                }

        # Validation : au moins un critère
        if not expr_parts:
            return {
                "status": "error",
                "message": "Aucun critère de suppression valide fourni.",
                "code": 400
            }

        # Combiner les expressions avec AND
        expr = " and ".join(expr_parts)

        print(f"Expression de suppression principale: {expr}")

        # Suppression dans la collection principale
        results = collection.delete(expr=expr)

        deleted_count = results.delete_count
        deleted_ids = list(results.primary_keys) if results.primary_keys else []

        print(f"Suppression principale: {deleted_count} ligne(s) supprimée(s) - IDs: {deleted_ids}")

        # Construction de la réponse de base
        response = {
            "status": "success",
            "collection": collection_name,
            "filters": {
                "ids": ids,
                "filters": filters,
                "expr": expr
            },
            "data": {
                "delete_count": deleted_count,
                "primary_keys": deleted_ids
            }
        }

        # Gestion de la suppression en cascade
        if cascade_enabled:
            cascade_result = _delete_cascade(
                collection_name=collection_name,
                cascade_filters=cascade_filters,
                main_filters=filters,
                main_delete_count=deleted_count
            )
            response["cascade"] = cascade_result
        else:
            response["cascade"] = {
                "enabled": False
            }

        return response

    except MilvusException as e:
        return {
            "status": "error",
            "message": f"Erreur Milvus: {str(e)}",
            "code": 500
        }

    except Exception as e:
        return {
            "status": "error",
            "message": f"Erreur inattendue: {str(e)}",
            "code": 500
        }


def _build_filters_expression(filters: Dict[str, Any]) -> str:
    """
    Construit une expression de filtre Milvus à partir d'un dictionnaire de filtres.

    Formats supportés:
    - Égalité simple: {"field": "value"} → field == "value"
    - Opérateurs: {"field": {"$gt": 10}} → field > 10

    Opérateurs supportés: $gt (>), $gte (>=), $eq (==), $ne (!=), $lt (<), $lte (<=), $in, $nin (not in), $like

    Args:
        filters: Dictionnaire de filtres

    Returns:
        Expression Milvus sous forme de chaîne
    """
    expr_parts = []

    for field_name, condition in filters.items():
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
    """
    Construit une condition unique de filtre.

    Args:
        field_name: Nom du champ
        operator: Opérateur ($gt, $gte, $eq, etc.)
        value: Valeur à comparer

    Returns:
        Expression de condition ou None si opérateur invalide
    """
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
            return f'{field_name} {milvus_op} "{value}"'
        else:
            return f"{field_name} {milvus_op} {value}"


def _delete_cascade(
    collection_name: str,
    cascade_filters: Optional[Dict[str, Any]],
    main_filters: Optional[Dict[str, Any]],
    main_delete_count: int
) -> Dict[str, Any]:
    """
    Gère la suppression en cascade dans la collection de correspondance.

    Args:
        collection_name: Nom de la collection principale
        cascade_filters: Filtres spécifiques pour la cascade (prioritaires)
        main_filters: Filtres de la collection principale (fallback)
        main_delete_count: Nombre de documents supprimés dans la collection principale

    Returns:
        Dict avec les résultats de la suppression en cascade
    """
    try:
        # Vérifier si des données ont été supprimées dans la collection principale
        if main_delete_count == 0:
            return {
                "enabled": True,
                "status": "skipped",
                "message": "Aucune donnée supprimée dans la collection principale"
            }

        # Vérifier si la collection a un mapping de cascade
        if collection_name not in MILVUS_COLLECTIONS_CASCADE_MAPPING:
            return {
                "enabled": True,
                "status": "skipped",
                "message": f"Aucun mapping de cascade défini pour la collection '{collection_name}'"
            }

        # Récupérer le nom de la collection de correspondance
        correspondance_collection_name = MILVUS_COLLECTIONS_CASCADE_MAPPING[collection_name]

        # Vérifier si la collection de correspondance existe dans Milvus
        if not utility.has_collection(correspondance_collection_name):
            return {
                "enabled": True,
                "collection": correspondance_collection_name,
                "status": "skipped",
                "message": "Collection de correspondance inexistante dans Milvus"
            }

        # Charger la collection de correspondance
        collection_correspondance = Collection(correspondance_collection_name)
        collection_correspondance.load()

        # Déterminer quels filtres utiliser pour la cascade
        filters_to_use = cascade_filters if cascade_filters else main_filters

        if not filters_to_use:
            return {
                "enabled": True,
                "collection": correspondance_collection_name,
                "status": "error",
                "message": "Aucun filtre disponible pour la suppression en cascade"
            }

        # Construire l'expression pour la cascade
        cascade_expr = _build_filters_expression(filters_to_use)

        if not cascade_expr:
            return {
                "enabled": True,
                "collection": correspondance_collection_name,
                "status": "error",
                "message": "Les filtres cascade n'ont généré aucune expression valide"
            }

        print(f"Expression de suppression en cascade: {cascade_expr}")

        # Suppression dans la collection de correspondance
        cascade_results = collection_correspondance.delete(expr=cascade_expr)

        cascade_delete_count = cascade_results.delete_count
        cascade_deleted_ids = list(cascade_results.primary_keys) if cascade_results.primary_keys else []

        print(f"Suppression en cascade dans '{correspondance_collection_name}': {cascade_delete_count} ligne(s) supprimée(s)")

        # Message informatif si aucune donnée supprimée
        message = None
        if cascade_delete_count == 0:
            message = "Aucune donnée correspondante trouvée dans la collection de correspondance"

        return {
            "enabled": True,
            "collection": correspondance_collection_name,
            "status": "success",
            "filters": filters_to_use,
            "expr": cascade_expr,
            "delete_count": cascade_delete_count,
            "primary_keys": cascade_deleted_ids,
            **({"message": message} if message else {})
        }

    except MilvusException as e:
        return {
            "enabled": True,
            "collection": correspondance_collection_name if 'correspondance_collection_name' in locals() else "unknown",
            "status": "error",
            "message": f"Erreur Milvus lors de la suppression en cascade: {str(e)}"
        }

    except Exception as e:
        return {
            "enabled": True,
            "collection": correspondance_collection_name if 'correspondance_collection_name' in locals() else "unknown",
            "status": "error",
            "message": f"Erreur inattendue lors de la suppression en cascade: {str(e)}"
        }


def _connect_to_milvus():
    """Établit la connexion à Milvus."""
    config = Configuration()
    connections.connect("default", host=config.ZILLIZ_URI, port=config.ZILLIZ_PORT, user=config.ZILLIZ_USER, password=config.ZILLIZ_PASSWORD)