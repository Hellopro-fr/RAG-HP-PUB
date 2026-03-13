"""
LLM client for reranking via gRPC llm-service.
Uses common_utils get_llm_chat_response with Gemini 3 Flash.
"""

import json
import logging
from typing import Dict, Any, Optional

from common_utils.grpc_clients.llm_client import get_llm_chat_response
from common_utils.grpc_clients.schemas.chat import ChatRequest

from app.config import settings

logger = logging.getLogger(__name__)


class GeminiClient:
    """LLM client for reranking via gRPC llm-service."""

    def __init__(self):
        self._model = "gemini-3-flash-preview"
        self._temperature = 0.1
        self._timeout = 120  # seconds

    async def generate_rerank_response(
        self, system_prompt: str, user_data_json: str
    ) -> Optional[Dict[str, Any]]:
        """
        Send enriched product data to LLM service for reranking analysis.

        Args:
            system_prompt: The system instruction for the LLM.
            user_data_json: JSON string of the formatted product data.

        Returns:
            Parsed JSON dict from the LLM response, or None on error.
        """
        try:
            # Combine system prompt and user data into one prompt
            combined_prompt = f"{system_prompt}\n\n{user_data_json}"

            logger.warning(
                "[RERANK-GEMINI] Sending request to llm-service via gRPC (model=%s)...",
                self._model,
            )

            chat_request = ChatRequest(
                prompt=combined_prompt,
                model=self._model,
                provider="gemini",
                temperature=self._temperature,
                max_tokens=8192,
                enable_thinking=False,
                options={
                    "top_p": 0.8,
                    "top_k": 20,
                },
            )

            logger.warning(
                "[RERANK-GEMINI] ChatRequest created: model=%s, provider=%s, temperature=%s",
                chat_request.model,
                chat_request.provider,
                chat_request.temperature,
            )

            response_dict = await get_llm_chat_response(chat_request)

            logger.warning(
                "[RERANK-GEMINI] gRPC response received: %s",
                str(response_dict)[:500],
            )

            if not response_dict:
                logger.warning("[RERANK-GEMINI] LLM service returned empty response")
                return None

            # Extract the full_message from the response
            full_message = response_dict.get("full_message", "")
            if not full_message:
                logger.warning("[RERANK-GEMINI] LLM response has no full_message")
                return None

            logger.warning(
                "[RERANK-GEMINI] full_message received (%d chars): %s",
                len(str(full_message)),
                str(full_message)[:500],
            )

            # If full_message is already a dict (parsed by protobuf), return it
            if isinstance(full_message, dict):
                logger.warning("[RERANK-GEMINI] full_message is already a dict, returning directly")
                return full_message

            # Otherwise parse as JSON string
            try:
                parsed = json.loads(full_message)
                logger.warning("[RERANK-GEMINI] Successfully parsed JSON response")
                return parsed
            except json.JSONDecodeError as e:
                logger.error(
                    f"[RERANK-GEMINI] Failed to parse LLM response as JSON: {e}\nResponse: {str(full_message)[:500]}"
                )
                return None

        except Exception as e:
            logger.error(f"[RERANK-GEMINI] LLM rerank generation error: {e}", exc_info=True)
            return None


# Singleton instance
gemini_client = GeminiClient()
