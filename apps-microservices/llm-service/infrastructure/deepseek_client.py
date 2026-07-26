import os
from openai import AsyncOpenAI
import re

MODEL_NAME = os.getenv("DEEPSEEK_MODEL_NAME", "deepseek-v4-flash")
class DeepSeekClient:
    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            base_url=os.getenv("DEEPSEEK_API_URL", "https://api.deepseek.com/v1"),
        )

    async def get_chat_completion(
        self,
        message_history,
        temperature: float,
        max_tokens: int,
        enable_thinking: bool,
        **kwargs,
    ) -> dict:
        try:
            model_name_deepseek = os.getenv("DEEPSEEK_MODEL_NAME", "deepseek-v4-flash")

            request_payload = {
                "model": model_name_deepseek,
                "messages": message_history,
                "temperature": temperature,
                "max_tokens": max_tokens,
                # DeepSeek V4 (deepseek-chat/deepseek-reasoner retirés le
                # 2026-07-24) : le thinking est un paramètre de requête, activé
                # PAR DÉFAUT — il faut le désactiver explicitement pour garder
                # le comportement/coût de l'ancien deepseek-chat.
                "extra_body": {
                    "thinking": {"type": "enabled" if enable_thinking else "disabled"}
                },
            }

            # if kwargs.get("options"):
            #     for key, value in kwargs["options"].items():
            #         request_payload[key] = value

            response = await self.client.chat.completions.create(**request_payload)

            content = "[ERREUR: Réponse inattendue du service LLM]"
            if response.choices:
                content = response.choices[0].message.content
                if not enable_thinking:
                    content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL)
                    content = re.sub(r"\s+", " ", content).strip()
            return {
                "full_message": content,
                "response": response.model_dump()
            }
        except Exception as e:
            return {
                "full_message": f"[ERREUR: {e}]",
                "response": {"error": str(e), "type": type(e).__name__}
            }

    async def stream_chat(
        self,
        message_history,
        temperature: float,
        max_tokens: int,
        enable_thinking: bool,
        **kwargs,
    ):
        try:
            request_payload = {
                "model": MODEL_NAME,
                "messages": message_history,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": True,
                # Flux : thinking toujours désactivé — ce chemin n'a jamais servi
                # le reasoner, et le parseur de deltas ne lit pas reasoning_content.
                "extra_body": {"thinking": {"type": "disabled"}},
            }

            # if kwargs.get("options"):
            #     for key, value in kwargs["options"].items():
            #         request_payload[key] = value

            stream = await self.client.chat.completions.create(**request_payload)

            async for chunk in stream:
                if chunk.choices:
                    content = chunk.choices[0].delta.content or ""
                    if not enable_thinking:
                        content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL)
                        content = re.sub(r"\s+", " ", content).strip()
                    yield content
        except Exception as e:
            yield f"[ERREUR: {e}]"
