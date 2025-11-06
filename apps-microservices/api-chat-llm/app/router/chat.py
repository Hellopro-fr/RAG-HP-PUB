import json
from re import A
from typing import List
from fastapi import APIRouter, HTTPException, Body, WebSocket, WebSocketDisconnect
from app.schemas.chat import  chatResponse
from common_utils.grpc_clients.schemas.chat import ChatRequest
# from app.core.search import search_in_milvus
from app.core.chat import get_chat_completion_response , get_chatgpt_chat_completion_response , get_deepseek_chat_completion_response , get_gemini_chat_completion_response, DeepSeek
from app.core.credentials import settings
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

class ConnexionManager:
    """
    Gère les connexions WebSocket actives.
    Chaque client est un "channel" unique.
    """
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        """Accepte une nouvelle connexion et l'ajoute à la liste."""
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"Nouvelle connexion acceptée: {websocket.client}. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        """Retire une connexion de la liste."""
        self.active_connections.remove(websocket)
        logger.info(f"Client déconnecté: {websocket.client}. Total: {len(self.active_connections)}")

    async def send_personal_message(self, message: dict, websocket: WebSocket):
        """Envoie un message JSON à un client spécifique."""
        await websocket.send_json(message)

# Crée une instance unique du gestionnaire qui sera partagée
manager = ConnexionManager()
    
@router.websocket("/ws/chat")
async def ws_search(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        # Keep the connection open to listen for messages
        while True:
            # Wait for a message from the client
            data = await websocket.receive_text()
            
            # For simplicity, we assume the data is the prompt
            prompt = data
            
            if not prompt.strip():
                await websocket.send_text("Error: Prompt cannot be empty.")
                continue

            # Instantiate DeepSeek
            deepseek_client = DeepSeek()
            
            full_text = ""
            last_chunk_data = {}
            # Stream the response back to the client
            async for chunk in deepseek_client.stream(prompt):
                if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                    content_to_send = chunk.choices[0].delta.content
                    full_text += content_to_send
                    await websocket.send_text(content_to_send) # Send chunks as they arrive for real-time display
                last_chunk_data = chunk.model_dump()
                
            await websocket.send_json({
                "type": "end",
                "full_content": full_text,
                "api_response": last_chunk_data
            })

    except WebSocketDisconnect:
        manager.disconnect(websocket)
        logger.info(f"WebSocket disconnected for client: {websocket.client}")
    except Exception as e:
        logger.error(f"Error in WebSocket: {e}", exc_info=True)
        # Attempt to send an error message before closing
        await websocket.close(code=1011, reason=f"An internal error occurred: {e}")
        manager.disconnect(websocket)

@router.post("/llm/chat", tags=["Chat - LLM"])
async def chat_completion_llm(request: ChatRequest = Body(...)):
    try:
        if not request.prompt.strip():
            raise ValueError("Le promt ne peut pas être vide.")        
        
        results = await get_chat_completion_response(request)
        return chatResponse(response=results.get("response", ""), api_response=results.get("api_response", {}), chat_model=settings.MODEL_NAME if settings.LLM_PROVIDER != "deepseek" else settings.DEEPSEEK_MODEL_NAME , temperature=request.temperature , time_elapsed=results.get("time_elapsed", None), options=request.options)
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
        return chatResponse(response=results.get("response", ""), api_response=results.get("api_response", {}), chat_model="gpt-4o-2024-11-20" , temperature=request.temperature , time_elapsed=results.get("time_elapsed", None), options=request.options)
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
        return chatResponse(response=results.get("response", ""), api_response=results.get("api_response", {}), chat_model="deepseek" , temperature=request.temperature , time_elapsed=results.get("time_elapsed", None), options=request.options)
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
        return chatResponse(response=results.get("response", ""), api_response=results.get("api_response", {}), chat_model="gemini-flash-1.5" , temperature=request.temperature , time_elapsed=results.get("time_elapsed", None), options=request.options)
    except ValueError as ve:
        logger.error(f"Erreur de validation (400): {ve}")
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Erreur interne du serveur (500): {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erreur interne du serveur: {e}")