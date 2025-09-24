# app/core/models.py
import queue
import asyncio
from typing import Optional
from pydantic import BaseModel, Field
from google.cloud import speech

class RecognitionConfigUpdate(BaseModel):
    """
    Pydantic model for validating incoming configuration updates from the client.
    """
    sample_rate: int = Field(48000, alias="sampleRate")
    language_code: str = Field("fr-FR", alias="languageCode")
    enable_punctuation: bool = Field(True, alias="enablePunctuation")
    interim_results: bool = Field(True, alias="interimResults")

class ClientState(BaseModel):
    """
    Maintains the state for a single WebSocket client connection.
    """
    client_id: int
    audio_queue: queue.Queue = Field(default_factory=queue.Queue)
    response_queue: queue.Queue = Field(default_factory=queue.Queue)
    processing_future: Optional[asyncio.Future] = None
    end_stream: bool = False
    
    # Google Speech-to-Text configurations
    recognition_config: speech.RecognitionConfig
    streaming_config: speech.StreamingRecognitionConfig

    class Config:
        # Allow arbitrary types like 'queue.Queue' and 'asyncio.Future'
        arbitrary_types_allowed = True

class OpenAIClientState(BaseModel):
    """
    Maintient l'état pour une connexion client WebSocket pour OPENAI.
    Utilise 'asyncio.Queue' qui est non-bloquante et essentielle pour les coroutines.
    """
    client_id: int
    audio_queue: asyncio.Queue = Field(default_factory=asyncio.Queue)
    response_queue: asyncio.Queue = Field(default_factory=asyncio.Queue)
    end_stream: bool = False
    # On réutilise RecognitionConfig pour la simplicité, même si seul sample_rate et language_code sont utilisés
    recognition_config: speech.RecognitionConfig

    class Config:
        arbitrary_types_allowed = True