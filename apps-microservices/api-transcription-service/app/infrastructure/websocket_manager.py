# app/infrastructure/websocket_manager.py
import asyncio
import base64
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Dict

from fastapi import WebSocket, WebSocketDisconnect
from google.cloud import speech
from pydantic import ValidationError

from app.core.models import ClientState, RecognitionConfigUpdate
from app.core.services import TranscriptionService

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class WebSocketManager:
    """
    Manages WebSocket connections, client states, and the transcription lifecycle.
    """
    def __init__(self, transcription_service: TranscriptionService):
        self.service = transcription_service
        self.executor = ThreadPoolExecutor(max_workers=10)
        self.clients: Dict[int, ClientState] = {}

    async def handle_connection(self, websocket: WebSocket):
        """Main handler for a new WebSocket connection."""
        client_id = id(websocket)
        logger.info(f"New client connected (ID: {client_id})")

        config, streaming_config = self.service.create_default_configs()
        client_state = ClientState(
            client_id=client_id,
            recognition_config=config,
            streaming_config=streaming_config,
        )
        self.clients[client_id] = client_state

        try:
            # Start the background audio processing task
            loop = asyncio.get_running_loop()
            client_state.processing_future = loop.run_in_executor(
                self.executor, self.service.process_audio_stream, client_state
            )

            # Run consumer and producer tasks concurrently
            consumer_task = asyncio.create_task(self._consume_audio(websocket, client_state))
            producer_task = asyncio.create_task(self._produce_transcripts(websocket, client_state))

            done, pending = await asyncio.wait(
                [consumer_task, producer_task], return_when=asyncio.FIRST_COMPLETED
            )
            for task in pending:
                task.cancel()

        except WebSocketDisconnect:
            logger.info(f"Client {client_id} disconnected.")
        except Exception as e:
            logger.error(f"Error handling client {client_id}: {e}")
            await self._send_error(websocket, str(e))
        finally:
            await self._cleanup_client(client_id)

    async def _consume_audio(self, websocket: WebSocket, client_state: ClientState):
        """Consumes audio data from the WebSocket and puts it in the client's queue."""
        async for message in websocket.iter_text():
            try:
                data = json.loads(message)

                if 'command' in data and data['command'] == 'end_stream':
                    client_state.end_stream = True
                    client_state.audio_queue.put(None)  # Signal end of audio
                    break

                elif 'config' in data:
                    config_update = RecognitionConfigUpdate(**data['config'])
                    self.service.update_client_configs(client_state, config_update)
                
                elif 'audio' in data:
                    audio_content = base64.b64decode(data['audio'])
                    client_state.audio_queue.put(audio_content)

            except json.JSONDecodeError:
                logger.warning(f"Received invalid JSON from client {client_state.client_id}")
            except ValidationError as e:
                logger.warning(f"Invalid config from client {client_state.client_id}: {e}")
            except Exception as e:
                logger.error(f"Error in _consume_audio for client {client_state.client_id}: {e}")
                raise

    async def _produce_transcripts(self, websocket: WebSocket, client_state: ClientState):
        """Produces transcripts from the client's response queue and sends them via WebSocket."""
        start_time = time.time()
        loop = asyncio.get_running_loop()

        while True:
            if time.time() - start_time >= 120:  # 2-minute limit
                logger.info(f"Stopping transcription for client {client_state.client_id} after 2 minutes.")
                await websocket.send_json({
                    "type": "end_stream",
                    "message": "Transcription limit of 2 minutes reached.",
                })
                client_state.end_stream = True
                client_state.audio_queue.put(None)
                break

            response = await loop.run_in_executor(None, client_state.response_queue.get)
            if response is None:
                break
            
            await websocket.send_json(response)

    async def _cleanup_client(self, client_id: int):
        """Cleans up resources for a disconnected client."""
        if client_id in self.clients:
            client_state = self.clients.pop(client_id)
            client_state.end_stream = True
            client_state.audio_queue.put(None) # Ensure the processing thread exits
            
            if client_state.processing_future:
                client_state.processing_future.cancel()
            
            logger.info(f"Cleaned up resources for client {client_id}")

    async def _send_error(self, websocket: WebSocket, error_message: str):
        """Sends a JSON error message to the client."""
        try:
            await websocket.send_json({"type": "error", "error": error_message})
        except WebSocketDisconnect:
            pass # Client already disconnected
