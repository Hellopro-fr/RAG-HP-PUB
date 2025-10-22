import asyncio

from infrastructure.vllm_client import VLLMClient


class ChatApplicationService:
    def __init__(self, vllm_client: VLLMClient):
        self.vllm_client = vllm_client

    async def handle_chat_stream(self, request_iterator):
        message_history = [
            {"role": "system", "content": "You are a helpful assistant."}
        ]

        try:
            first_request = await anext(request_iterator)
            temperature = (
                first_request.temperature
                if first_request.HasField("temperature")
                else 0.7
            )
            max_tokens = (
                first_request.max_tokens
                if first_request.HasField("max_tokens")
                else 1024
            )
            enable_thinking = (
                first_request.enable_thinking
                if first_request.HasField("enable_thinking")
                else False
            )
            options = first_request.options if first_request.HasField("options") else {}

            message_history.append({"role": "user", "content": first_request.message})
        except StopAsyncIteration:
            return

        while True:
            response_generator = self.vllm_client.stream_chat(
                message_history, temperature, max_tokens, enable_thinking, options=options
            )

            full_response_buffer = ""
            async for chunk in response_generator:
                yield chunk
                full_response_buffer += chunk

            message_history.append(
                {"role": "assistant", "content": full_response_buffer}
            )

            try:
                next_request = await anext(request_iterator)
                message_history.append(
                    {"role": "user", "content": next_request.message}
                )
            except StopAsyncIteration:
                break

    async def handle_chat_completion(
        self, message: str, temperature: float, max_tokens: int, enable_thinking: bool, **kwargs
    ) -> str:
        message_history = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": message},
        ]

        return await self.vllm_client.get_chat_completion(
            message_history, temperature, max_tokens, enable_thinking, options=kwargs.get("options", {})
        )

    async def handle_chat_batch_completion(
        self,
        messages: list[str],
        temperature: float,
        max_tokens: int,
        enable_thinking: bool,
        **kwargs
    ) -> list[str]:
        """
        Gère une liste de requêtes de chat en parallèle et retourne les réponses complètes.
        """
        if not messages:
            return []

        # Crée une tâche asynchrone pour chaque message
        tasks = [
            self.handle_chat_completion(msg, temperature, max_tokens, enable_thinking, options=kwargs.get("options", {}))
            for msg in messages
        ]

        # Exécute toutes les tâches en parallèle et attend leurs résultats
        # vLLM va automatiquement batcher ces requêtes concurrentes en interne.
        responses = await asyncio.gather(*tasks)
        return responses
