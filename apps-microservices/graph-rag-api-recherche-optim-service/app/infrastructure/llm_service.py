import logging
from typing import Dict, Any, List, Optional

from common_utils.grpc_clients import llm_client
from common_utils.grpc_clients.schemas.chat import ChatRequest, ChatProvider
from app.config import settings


class LLMService:
    """Service to interact with LLM via gRPC."""

    async def generate_answer(self, system_prompt: str, user_prompt: str) -> str:
        """
        Generates a simple text response.
        """
        full_prompt = f"{system_prompt}\n\nUser Input: {user_prompt}"

        chat_req = ChatRequest(
            prompt=full_prompt,
            provider=settings.LLM_PROVIDER,  # 'gemini', 'openai', etc.
            model=settings.LLM_MODEL_NAME,
            temperature=0.3,
            max_tokens=2048,
        )

        try:
            response_dict = await llm_client.get_llm_chat_response(chat_req)
            # The gRPC client returns a dict. We need to extract the content.
            # Assuming the structure matches what common_utils returns.
            # Usually it returns the full message content directly or a structured dict.
            # Based on common_utils implementation: return MessageToDict(response.full_message)
            # If full_message is a string in the proto, it might be wrapped.

            # Adjust based on actual proto definition of ChatResponse.full_message
            # If it's just a string content:
            if "content" in response_dict:
                return response_dict["content"]
            # Fallback if the dict is the message itself
            return str(response_dict)

        except Exception as e:
            logging.error(f"LLM Generation Error: {e}")
            return "I encountered an error generating the response."

    async def invoke_chain(self, prompt_template: str, inputs: Dict[str, Any]) -> str:
        """
        Helper to format a prompt and call the LLM, mimicking LangChain's invoke.
        """
        formatted_prompt = prompt_template.format(**inputs)
        return await self.generate_answer("", formatted_prompt)


llm_service = LLMService()
