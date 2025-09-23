# app/core/services.py
import asyncio
import json
import logging
import websockets
from config.settings import settings
from google.cloud import speech
from app.core.models import ClientState, RecognitionConfigUpdate, OpenAIClientState

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TranscriptionService:
    """
    Service responsible for handling the audio transcription logic
    using Google's Speech-to-Text API.
    """
    def __init__(self, speech_client: speech.SpeechClient):
        self.client = speech_client

    def create_default_configs(self) -> tuple[speech.RecognitionConfig, speech.StreamingRecognitionConfig]:
        """Creates default recognition and streaming configurations."""
        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
            sample_rate_hertz=48000,
            language_code="fr-FR",
            enable_automatic_punctuation=True,
        )
        streaming_config = speech.StreamingRecognitionConfig(
            config=config, interim_results=True
        )
        return config, streaming_config

    def update_client_configs(self, client_state: ClientState, config_update: RecognitionConfigUpdate):
        """Updates a client's configurations based on received data."""
        client_state.recognition_config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
            sample_rate_hertz=config_update.sample_rate,
            language_code=config_update.language_code,
            enable_automatic_punctuation=config_update.enable_punctuation,
        )
        client_state.streaming_config = speech.StreamingRecognitionConfig(
            config=client_state.recognition_config,
            interim_results=config_update.interim_results,
        )
        logger.info(f"Configuration updated for client {client_state.client_id}")

    def process_audio_stream(self, client_state: ClientState):
        """
        Processes the audio stream from a client's queue and sends it to Google STT.
        This function is designed to be run in a separate thread.
        """
        try:
            def request_generator():
                while not client_state.end_stream:
                    audio_data = client_state.audio_queue.get()
                    if audio_data is None:
                        break
                    yield speech.StreamingRecognizeRequest(audio_content=audio_data)

            responses = self.client.streaming_recognize(
                config=client_state.streaming_config,
                requests=request_generator(),
            )

            for response in responses:
                if not response.results:
                    continue
                
                result = response.results[0]
                if not result.alternatives:
                    continue
                
                transcript_data = {
                    "transcript": result.alternatives[0].transcript,
                    "confidence": result.alternatives[0].confidence,
                    "isFinal": result.is_final,
                    "type": "transcript",
                    "clientId": client_state.client_id,
                }
                client_state.response_queue.put(transcript_data)

        except Exception as e:
            logger.error(f"Error in process_audio_stream for client {client_state.client_id}: {e}")
            client_state.response_queue.put({
                "error": str(e),
                "type": "error",
                "clientId": client_state.client_id,
            })
        finally:
            # Signal that transcription is complete
            client_state.response_queue.put(None)

class OpenAIRealtimeService:
    """
    Gère la connexion et la communication avec la NOUVELLE API Realtime Transcription d'OpenAI.
    """
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.openai_url = "wss://api.openai.com/v1/realtime?intent=transcription"
        self.auth_headers = {
            "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
            "OpenAI-Beta": "realtime=v1"
        }

    async def manage_openai_connection(self, client_state: OpenAIClientState):
        
        try:
            async with websockets.connect(
                self.openai_url,
                extra_headers=self.auth_headers
            ) as openai_ws:
                
                self.logger.info("Connexion à OpenAI réussie. En attente de la confirmation de session initiale...")
                try:
                    config_message = await asyncio.wait_for(client_state.audio_queue.get(), timeout=10.0)
                    if config_message is None or 'config' not in config_message:
                        raise ValueError("Message de configuration initial non reçu ou invalide.")
                    
                    sample_rate = config_message['config']['sampleRate']
                    client_state.recognition_config.sample_rate_hertz = sample_rate
                    client_state.audio_queue.task_done()
                    self.logger.info(f"Fréquence d'échantillonnage reçue du client : {sample_rate}Hz")
                except Exception as e:
                    self.logger.error(f"Erreur lors de la réception de la config client: {e}")
                    return

                session_update_payload = {
                    "type": "transcription_session.update",
                    "session": {
                        "input_audio_transcription": {
                            "model": "gpt-4o-transcribe",
                            "language": client_state.recognition_config.language_code,
                        },
                        "turn_detection": {
                            "type": "server_vad"
                        }
                    }
                }
                await openai_ws.send(json.dumps(session_update_payload))
                self.logger.info(f"Demande de mise à jour de la session envoyée avec payload: {session_update_payload}")

                try:
                    while True:
                        response_str = await asyncio.wait_for(openai_ws.recv(), timeout=5.0)
                        response_data = json.loads(response_str)
                        if response_data.get("type") in ["transcription_session.created", "transcription_session.updated"]:
                            self.logger.info(f"✅ Session OpenAI confirmée et prête. Type: {response_data.get('type')}")
                            break
                        else:
                            self.logger.info(f"Message intermédiaire reçu, en attente de confirmation : {response_data.get('type')}")
                except Exception as e:
                    self.logger.error(f"N'a pas pu confirmer la création de la session OpenAI : {e}")
                    return

                await client_state.response_queue.put({"type": "server_ready"})
                self.logger.info("Message 'server_ready' envoyé au client.")
                
                forward_task = asyncio.create_task(self._forward_audio_to_openai(openai_ws, client_state))
                receive_task = asyncio.create_task(self._receive_transcripts_from_openai(openai_ws, client_state))

                done, pending = await asyncio.wait(
                    [forward_task, receive_task], return_when=asyncio.FIRST_COMPLETED
                )
                for task in pending:
                    task.cancel()

        except Exception as e:
            error_msg = f"Erreur dans manage_openai_connection: {e}"
            self.logger.error(error_msg)
            await client_state.response_queue.put({"type": "error", "error": error_msg})
        finally:
            await client_state.response_queue.put(None)

    async def _forward_audio_to_openai(self, openai_ws, client_state: OpenAIClientState):
        while not client_state.end_stream:
            try:
                message_from_client = await client_state.audio_queue.get()
                
                if message_from_client and 'audio' in message_from_client:
                    audio_data_base64 = message_from_client['audio']
                    message_to_openai = {
                        "type": "input_audio_buffer.append",
                        "audio": audio_data_base64,
                    }
                    await openai_ws.send(json.dumps(message_to_openai))
                if message_from_client and 'command' in message_from_client and message_from_client['command'] == 'end_stream':
                    client_state.end_stream = True
                
                client_state.audio_queue.task_done()

            except asyncio.CancelledError:
                break
            except TypeError:
                self.logger.warning("Message 'None' reçu dans la queue audio, fin de la boucle.")
                client_state.end_stream = True
        self.logger.info(f"Arrêt de la transmission audio vers OpenAI pour le client {client_state.client_id}")

    async def _receive_transcripts_from_openai(self, openai_ws, client_state: OpenAIClientState):
        async for message in openai_ws:
            try:
                data = json.loads(message)
                self.logger.info(f"Reçu d'OpenAI: {data}")

                event_type = data.get("type")
                transcript = None
                is_final = False

                if event_type == "conversation.item.input_audio_transcription.delta":
                    transcript = data.get("delta")
                    is_final = False
                elif event_type == "conversation.item.input_audio_transcription.completed":
                    transcript = data.get("transcript")
                    is_final = True

                if transcript is not None:
                    client_message = {
                        "type": "transcript",
                        "transcript": transcript,
                        "isFinal": is_final,
                        "clientId": client_state.client_id
                    }
                    await client_state.response_queue.put(client_message)

            except (json.JSONDecodeError, asyncio.CancelledError):
                break
        self.logger.info(f"Arrêt de la réception des transcriptions d'OpenAI pour le client {client_state.client_id}")