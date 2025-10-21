from fastapi import APIRouter, HTTPException, Body
from app.schemas.chat import  chatResponse
from common_utils.grpc_clients.schemas.chat import ChatRequest
# from app.core.search import search_in_milvus
from app.core.chat import get_chat_completion_response , get_chatgpt_chat_completion_response , get_deepseek_chat_completion_response , get_gemini_chat_completion_response
from app.core.credentials import settings
import logging

router = APIRouter()
logger = logging.getLogger(__name__)
    

@router.post("/llm/chat", tags=["Chat - LLM"])
async def chat_completion_llm(request: ChatRequest = Body(...)):
    try:
        # logger.info(f"Requête chat completion sur llm : {request.prompt}")
        if not request.prompt.strip():
            raise ValueError("Le promt ne peut pas être vide.")        
        
        results = await get_chat_completion_response(request)
        # logger.info(f"Résultats de la chat complesion: {results}")
        # return chatResponse(response=results["response"], chat_model="Qwen/Qwen3-14B-AWQ" , temperature=request.temperature , time_elapsed=results.get("time_elapsed", None))
        return chatResponse(response=results.get("response", ""), chat_model=settings.MODEL_NAME , temperature=request.temperature , time_elapsed=results.get("time_elapsed", None))
    except ValueError as ve:
        logger.error(f"Erreur de validation (400): {ve}")
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Erreur interne du serveur (500): {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erreur interne du serveur: {e}")

@router.post("/llm/chat/chatgpt", tags=["Chat - Chatgpt"])
async def chatgpt_chat_completion_llm(request: ChatRequest = Body(...)):
    try:
        # logger.info(f"Requête chat completion sur Chatgpt : {request.prompt}")
        if not request.prompt.strip():
            raise ValueError("Le promt ne peut pas être vide.")        
        
        results = await get_chatgpt_chat_completion_response(request)
        # logger.info(f"Résultats de la chat complesion: {results}")
        return chatResponse(response=results["response"], chat_model="gpt-4o-2024-11-20" , temperature=request.temperature , time_elapsed=results.get("time_elapsed", None))
    except ValueError as ve:
        logger.error(f"Erreur de validation (400): {ve}")
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Erreur interne du serveur (500): {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erreur interne du serveur: {e}")
    
@router.post("/llm/chat/deepseek", tags=["Chat - DeepSeek"])
async def deepseek_chat_completion_llm(request: ChatRequest = Body(...)):
    try:
        # logger.info(f"Requête chat completion sur DeepSeek : {request.prompt}")
        if not request.prompt.strip():
            raise ValueError("Le promt ne peut pas être vide.")        
        
        results = await get_deepseek_chat_completion_response(request)
        # logger.info(f"Résultats de la chat complesion: {results}")
        return chatResponse(response=results["response"], chat_model="deepseek" , temperature=request.temperature , time_elapsed=results.get("time_elapsed", None))
    except ValueError as ve:
        logger.error(f"Erreur de validation (400): {ve}")
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Erreur interne du serveur (500): {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erreur interne du serveur: {e}")
    
@router.post("/llm/chat/gemini", tags=["Chat - Gemini"])
async def deepseek_chat_completion_llm(request: ChatRequest = Body(...)):
    try:
        # logger.info(f"Requête chat completion sur Gemini : {request.prompt}")
        if not request.prompt.strip():
            raise ValueError("Le promt ne peut pas être vide.")        
        
        results = await get_gemini_chat_completion_response(request)
        # logger.info(f"Résultats de la chat complesion: {results}")
        return chatResponse(response=results["response"], chat_model="gemini-flash-1.5" , temperature=request.temperature , time_elapsed=results.get("time_elapsed", None))
    except ValueError as ve:
        logger.error(f"Erreur de validation (400): {ve}")
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Erreur interne du serveur (500): {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erreur interne du serveur: {e}")