from typing import List
from fastapi import APIRouter, HTTPException, Body
from app.schemas.embedding import EmbeddingRequest
from app.schemas.reranking import RerankingRequest

import logging
import os
import asyncio
from common_utils.grpc_clients import (
    embedding_client,
    reranking_client
)
from common_utils.embedding.Embedding import Embedding

log_format = "%(asctime)s - %(levelname)s - [WORKER_PID:%(process)d] - %(message)s"
logging.basicConfig(level=logging.INFO, format=log_format)
logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/embedding", tags=["Embedding"])
async def embedded(request: EmbeddingRequest):
    try:
        logger.info(f"Requête reçue pour embedding: {request.text}")
        if not request.text.strip():
            raise ValueError("Le prompt ne peut pas être vide.")
        embedding_service = Embedding()
        results = await embedding_service.embed_data_clean(request.model_dump())
        
        if not results:
            raise ValueError("Aucun contenu textuel valide trouvé pour l'embedding après nettoyage.")
        
        return results
    except ValueError as ve:
        logger.error(f"Erreur de validation (400): {ve}")
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Erreur interne du serveur (500): {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erreur interne du serveur: {e}")
    
@router.post("/reranking")
async def rerank(request: RerankingRequest):
    try:
        if not request.query.strip() or not request.documents:
            raise ValueError("Le query et les documents ne peuvent pas être vide.")
        results = await reranking_client.rerank_documents(request.query, request.documents)
        if not results or not any(results): # Check if results is empty or contains only empty elements
            raise ValueError("Aucun contenu reranked avec le query trouvé ou les documents sont vides après reranking.")
        return results
    except ValueError as ve:
        logger.error(f"Erreur de validation (400): {ve}")
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Erreur interne du serveur (500): {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erreur interne du serveur: {e}")