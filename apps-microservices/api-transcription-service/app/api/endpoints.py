# app/api/endpoints.py
from fastapi import APIRouter, WebSocket, Depends, Query, status, HTTPException
from google.cloud import speech

from app.infrastructure.websocket_manager import WebSocketManager
from app.core.services import TranscriptionService
from config.settings import settings

from app.infrastructure.websocket_manager import OpenAIRealtimeWebSocketManager
from app.core.services import OpenAIRealtimeService

router = APIRouter()

# --- Dependency Injection ---

def get_speech_client() -> speech.SpeechClient:
    """Dependency to create a Google SpeechClient instance."""
    return speech.SpeechClient()

def get_transcription_service(
    client: speech.SpeechClient = Depends(get_speech_client),
) -> TranscriptionService:
    """Dependency to create a TranscriptionService instance."""
    return TranscriptionService(speech_client=client)

def get_websocket_manager(
    service: TranscriptionService = Depends(get_transcription_service),
) -> WebSocketManager:
    """Dependency to create a WebSocketManager instance."""
    return WebSocketManager(transcription_service=service)

def get_openai_realtime_service() -> OpenAIRealtimeService:
    return OpenAIRealtimeService()

def get_openai_realtime_manager(
    service: OpenAIRealtimeService = Depends(get_openai_realtime_service),
) -> OpenAIRealtimeWebSocketManager:
    return OpenAIRealtimeWebSocketManager(transcription_service=service)

# --- WebSocket Endpoint ---

@router.websocket("/ws/google/transcription")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(...),
    manager: WebSocketManager = Depends(get_websocket_manager),
):
    """
    WebSocket endpoint for real-time audio transcription.
    Authenticates using a simple token from query parameters.
    """
    if token != settings.AUTH_TOKEN:
        # Using close instead of HTTPException for WebSockets
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()
    await manager.handle_connection(websocket)

@router.websocket("/ws/openai/transcription")
async def openai_realtime_websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(...),
    manager: OpenAIRealtimeWebSocketManager = Depends(get_openai_realtime_manager),
):
    """
    Point de terminaison WebSocket pour la transcription avec la nouvelle API Realtime d'OpenAI.
    """
    if token != settings.AUTH_TOKEN:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()
    await manager.handle_connection(websocket)