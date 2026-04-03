"""
Direct Gemini SDK client for LLM-based reranking.
Uses google-genai package with Gemini 3 Flash and retry logic.
"""

import asyncio
import json
import logging
from typing import Dict, Any, Optional

from google import genai
from google.genai import types, errors
from tenacity import (
    Retrying,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception,
)

from app.config import settings

logger = logging.getLogger(__name__)


def make_serializable(obj):
    """Parcourt récursivement l'objet pour convertir les bytes en hex string."""
    if isinstance(obj, bytes):
        return obj.hex()  # Convertit b'\xe6...' en string 'e6...'
    if isinstance(obj, dict):
        return {k: make_serializable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [make_serializable(v) for v in obj]
    return obj


def is_retryable_error(exception):
    """
    Checks if the exception is a Google GenAI 503 or 429 error.
    """
    code = getattr(exception, "status_code", None)

    if code is None:
        code = getattr(exception, "code", None)

    return code in [503, 429]


class GeminiClient:
    """Direct Gemini SDK client for reranking with retry logic."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        # model: str = "gemini-3-flash-preview",
        # model: str = "gemini-2.5-flash-lite",
        model: str = "gemini-3.1-flash-lite-preview",
        max_retries: int = 10,
    ):
        self.api_key = api_key or settings.GEMINI_API_KEY
        self.model = model
        self.max_retries = max_retries
        self._temperature = 0.1
        self._timeout = 120  # seconds
        self.client = genai.Client(api_key=self.api_key)

    def chat(
        self,
        prompt: str,
        temperature: Optional[float] = None,
        thinking_level: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Envoie un prompt à Gemini avec retry automatique

        Args:
            prompt: Le prompt à envoyer

        Returns:
            Dict avec 'message', 'api_response' ou 'code', 'error', 'content', 'response'
        """
        response = None

        try:
            # Configure Tenacity pour les retries
            retryer = Retrying(
                stop=stop_after_attempt(self.max_retries),
                wait=wait_exponential(multiplier=1, min=1, max=60),
                retry=retry_if_exception(is_retryable_error),
                reraise=True,
            )

            for attempt in retryer:
                with attempt:
                    # Log seulement sur les retries
                    if attempt.retry_state.attempt_number > 1:
                        logger.info(
                            f"Retry Gemini API... Tentative {attempt.retry_state.attempt_number}"
                        )

                    logger.info(
                        f"Gemini API tentative: {attempt.retry_state.attempt_number}"
                    )

                    effective_temperature = (
                        temperature if temperature is not None else self._temperature
                    )
                    # Build thinking config if thinking_level is provided
                    thinking_config = (
                        types.ThinkingConfig(
                            thinking_level=thinking_level,
                            include_thoughts=True,
                        )
                        if thinking_level is not None
                        else None
                    )
                    response = self.client.models.generate_content(
                        model=self.model,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            temperature=effective_temperature,
                            response_mime_type="application/json",
                            max_output_tokens=4096,
                            # thinking_config=thinking_config,
                        ),
                    )

        except errors.ClientError as e:
            logger.error(
                f"Gemini ClientError: {e.message} (Code: {e.code}) type: {type(e)}"
            )
            return {
                "code": e.code,
                "error": e.message,
                "content": None,
                "response": {
                    "code": e.code,
                    "message": e.message,
                    "status": getattr(e, "status", "UNKNOWN"),
                },
            }

        except Exception as e:
            logger.error(f"Erreur inattendue dans Gemini: {e}")
            return {
                "code": 500,
                "error": str(e),
                "content": None,
                "response": {},
            }

        # Succès
        api_response_dict = response.model_dump()
        safe_api_response = make_serializable(api_response_dict)

        return {"message": response.text, "api_response": safe_api_response}

    async def generate_rerank_response(
        self,
        system_prompt: str,
        # user_data_json: str,
        temperature: Optional[float] = None,
        thinking_level: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Send enriched product data to Gemini for reranking analysis.

        Args:
            system_prompt: The system instruction for the LLM.
            user_data_json: JSON string of the formatted product data.

        Returns:
            Parsed JSON dict from the LLM response, or None on error.
        """
        try:
            # Combine system prompt and user data into one prompt
            # combined_prompt = f"{system_prompt}\n\n{user_data_json}"
            combined_prompt = f"{system_prompt}"

            logger.warning(
                "[RERANK-GEMINI] Sending request to Gemini (model=%s)...", self.model
            )
            # logger.warning("[RERANK-GEMINI] Combined prompt: %s", combined_prompt)

            # Run the synchronous chat call in a thread pool to avoid blocking the event loop
            result = await asyncio.wait_for(
                asyncio.to_thread(
                    self.chat, combined_prompt, temperature, thinking_level
                ),
                timeout=self._timeout,
            )

            # logger.warning(
            #     "[RERANK-GEMINI] Gemini response received: %s",
            #     str(result)[:500],
            # )

            # Check for error in result
            if "error" in result:
                logger.warning(
                    "[RERANK-GEMINI] Gemini returned error: code=%s, error=%s",
                    result.get("code"),
                    result.get("error"),
                )
                return None

            # Extract message from the result
            response_text = result.get("message", "")
            if not response_text:
                logger.warning("[RERANK-GEMINI] Gemini returned empty message")
                return None

            # logger.warning(
            #     "[RERANK-GEMINI] Gemini message received (%d chars): %s",
            #     len(response_text),
            #     response_text[:500],
            # )

            # Parse JSON response
            try:
                parsed = json.loads(response_text)
                logger.warning("[RERANK-GEMINI] Successfully parsed JSON response")
                return parsed
            except json.JSONDecodeError as e:
                logger.error(
                    f"[RERANK-GEMINI] Failed to parse Gemini response as JSON: {e}\nResponse: {response_text[:500]}"
                )
                return None

        except asyncio.TimeoutError:
            logger.error(
                f"[RERANK-GEMINI] Gemini call timed out after {self._timeout}s"
            )
            return None
        except Exception as e:
            logger.error(
                f"[RERANK-GEMINI] Gemini rerank generation error: {e}", exc_info=True
            )
            return None


# Singleton instance
gemini_client = GeminiClient()
