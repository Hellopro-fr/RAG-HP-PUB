from typing import List
from fastapi import APIRouter, HTTPException, Body
from app.schemas.embedding import EmbeddingRequest
# from app.core.search import search_in_milvus
from app.core.recherche import search_in_milvus as search
import logging
import os
import asyncio
from common_utils.grpc_clients import (
    embedding_client
)

log_format = "%(asctime)s - %(levelname)s - [WORKER_PID:%(process)d] - %(message)s"
logging.basicConfig(level=logging.INFO, format=log_format)
logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/embedding", tags=["Embedding"])
async def embedded(request: EmbeddingRequest = Body(...)) -> List[float]:
    try:
        logger.info(f"Requête reçue pour embedding: {request.prompt}")
        if not request.prompt.strip():
            raise ValueError("Le prompt ne peut pas être vide.")
        
        results = await asyncio.to_thread(embedding_client.get_embedding, request)
        return results
    except ValueError as ve:
        logger.error(f"Erreur de validation (400): {ve}")
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Erreur interne du serveur (500): {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erreur interne du serveur: {e}")