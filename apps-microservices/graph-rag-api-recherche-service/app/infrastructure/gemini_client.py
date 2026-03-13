"""
Direct Gemini SDK client for LLM-based reranking.
Uses google-genai package with Gemini 2.5 Flash.
"""

import asyncio
import json
import logging
from typing import Dict, Any, Optional

from google import genai
from google.genai import types

from app.config import settings

logger = logging.getLogger(__name__)


class GeminiClient:
    """Direct Gemini SDK client for reranking."""

    def __init__(self):
        self._client = None
        self._model = "gemini-3-flash-preview"
        self._temperature = 0.1
        self._timeout = 120  # seconds

    def _get_client(self) -> genai.Client:
        if self._client is None:
            api_key = settings.GEMINI_API_KEY
            if not api_key:
                raise ValueError("GEMINI_API_KEY is not set in settings")
            self._client = genai.Client(api_key=api_key)
        return self._client

    def _sync_generate(self, system_prompt: str, user_data_json: str) -> Optional[str]:
        """Synchronous generate_content call (runs in thread pool)."""
        client = self._get_client()
        response = client.models.generate_content(
            model=self._model,
            contents=user_data_json,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=self._temperature,
                response_mime_type="application/json",
            ),
        )
        return response.text

    async def generate_rerank_response(
        self, system_prompt: str, user_data_json: str
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
            logger.info("[RERANK-GEMINI] Sending request to Gemini (model=%s)...", self._model)

            # Run the synchronous SDK call in a thread pool to avoid blocking the event loop
            response_text = await asyncio.wait_for(
                asyncio.to_thread(self._sync_generate, system_prompt, user_data_json),
                timeout=self._timeout,
            )

            if not response_text:
                logger.warning("[RERANK-GEMINI] Gemini returned empty response")
                return None

            logger.info("[RERANK-GEMINI] Gemini response received (%d chars)", len(response_text))

            # Parse JSON response
            try:
                parsed = json.loads(response_text)
                return parsed
            except json.JSONDecodeError as e:
                logger.error(
                    f"[RERANK-GEMINI] Failed to parse Gemini response as JSON: {e}\nResponse: {response_text[:500]}"
                )
                return None

        except asyncio.TimeoutError:
            logger.error(f"[RERANK-GEMINI] Gemini call timed out after {self._timeout}s")
            return None
        except Exception as e:
            logger.error(f"[RERANK-GEMINI] Gemini rerank generation error: {e}", exc_info=True)
            return None


# Singleton instance
gemini_client = GeminiClient()

