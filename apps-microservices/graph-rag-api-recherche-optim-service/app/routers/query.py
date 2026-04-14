from fastapi import APIRouter, HTTPException
from app.domain.models import QueryRequest, QueryResponse
from app.services.rag_service import rag_service

router = APIRouter()


@router.post("", response_model=QueryResponse)
async def intelligent_search(request: QueryRequest):
    """
    Execute a RAG query: Hybrid Search + LLM Answer.
    """
    try:
        response = await rag_service.process_query(request.query, request.route)
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
