from fastapi import APIRouter, HTTPException, Body
from app.schemas.chat import  chatResponse
from common_utils.grpc_clients.schemas.chat import ChatRequest
# from app.core.search import search_in_milvus
from app.core.chat import get_chat_completion_response 

import logging

router = APIRouter()
logger = logging.getLogger(__name__)
    

@router.post("/llm/chat", tags=["Chat - LLM"])
async def chat_completion_llm(request: ChatRequest = Body(...)):
    try:
        logger.info(f"Requête chat completion sur llm : {request.prompt}")
        if not request.prompt.strip():
            raise ValueError("Le promt ne peut pas être vide.")        
        
        results = await get_chat_completion_response(request)
        logger.info(f"Résultats de la chat complesion: {results}")
        return chatResponse(response=results["response"], chat_model=request.chat_model , temperature=request.temperature , time_elapsed=results.get("time_elapsed", None))
    except ValueError as ve:
        logger.error(f"Erreur de validation (400): {ve}")
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Erreur interne du serveur (500): {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erreur interne du serveur: {e}")