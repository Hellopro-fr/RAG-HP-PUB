from fastapi import APIRouter, HTTPException, status
from typing import List
import logging
import time

from app.domain.models import (
    CypherQueryRequest,
    CypherQueryResponse,
    CategorieCountResponse,
)
from app.infrastructure.clients import clients

router = APIRouter()


@router.post("/cypher", response_model=CypherQueryResponse)
async def execute_raw_cypher(request: CypherQueryRequest):
    """
    **WARNING: ADMIN ONLY**
    Executes a raw Cypher query against the Neo4j database via gRPC.
    """
    start_time = time.perf_counter()

    try:
        results = await clients.execute_cypher(request.query, request.params)

        logging.info(f"Results: {results}")
        end_time = time.perf_counter()
        duration = end_time - start_time

        if isinstance(results, dict):
            result_data = results.get("results", [])
            query_time = results.get("query_time", 0)
        else:
            result_data = results if results is not None else []
            query_time = 0

        return CypherQueryResponse(
            results=result_data,
            info={
                "execution_time_seconds": round(duration, 4),
                "query_time": round(query_time, 4),
                "record_count": len(result_data),
            },
        )

    except Exception as e:
        logging.error(f"Error executing raw Cypher query: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cypher execution failed: {str(e)}",
        )


@router.get("/count", response_model=List[CategorieCountResponse])
async def get_category_counts():
    """
    Returns the count of distinct Fournisseurs and Produits per Categorie.
    """
    query = """
    MATCH (p:Produit)-[:EST_PROPOSE_PAR]-(f:Fournisseur)
    WHERE p.est_actif = true
    RETURN p.id_categorie AS Categorie, count(DISTINCT f) AS Nb_Fournisseurs, count(DISTINCT p) AS Nb_produits
    ORDER BY Categorie ASC
    """

    try:
        results = await clients.execute_cypher(query)

        return [
            CategorieCountResponse(
                id_categorie=record.get("Categorie"),
                fournisseur=record.get("Nb_Fournisseurs", 0),
                produit=record.get("Nb_produits", 0),
            )
            for record in results
        ]

    except Exception as e:
        logging.error(f"Error in GET /admin/count: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal error occurred while retrieving category counts.",
        )
