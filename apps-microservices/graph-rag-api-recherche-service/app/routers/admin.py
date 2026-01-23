from fastapi import APIRouter, HTTPException, status
import logging
import time

from app.domain.models import CypherQueryRequest, CypherQueryResponse
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

        end_time = time.perf_counter()
        duration = end_time - start_time

        return CypherQueryResponse(
            results=results,
            info={
                "execution_time_seconds": round(duration, 4),
                "record_count": len(results),
            },
        )

    except Exception as e:
        logging.error(f"Error executing raw Cypher query: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cypher execution failed: {str(e)}",
        )
