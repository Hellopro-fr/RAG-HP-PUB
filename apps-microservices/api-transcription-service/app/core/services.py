# app/core/services.py
import logging
from google.cloud import speech
from app.core.models import ClientState, RecognitionConfigUpdate

# Configure logging
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
