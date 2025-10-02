import httpx
import json
import os
import logging

VLLM_API_URL = os.getenv("VLLM_API_URL", "http://vllm-server:8000/v1/chat/completions")
MODEL_NAME = os.getenv("MODEL_NAME", "Qwen/Qwen3-14B-AWQ")

class VLLMClient:
    def __init__(self):
        # Créer une seule instance client avec un timeout généreux
        # et des limites de connexion pour la robustesse.
        timeout_config = httpx.Timeout(None, connect=10.0)
        limits_config = httpx.Limits(max_connections=100, max_keepalive_connections=20)
        self.http_client = httpx.AsyncClient(timeout=timeout_config, limits=limits_config)

    async def stream_chat(self, message_history, temperature: float, max_tokens: int, enable_thinking: bool):
        try:
            request_payload = {
                "model": MODEL_NAME,
                "messages": message_history,
                "stream": True,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "chat_template_kwargs": {"enable_thinking": enable_thinking}
            }
            # Utiliser l'instance partagée self.http_client
            async with self.http_client.stream("POST", VLLM_API_URL, json=request_payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    # ... (logique de parsing inchangée)
                    if line.startswith('data: '):
                        data_str = line[len('data: '):].strip()
                        if data_str == '[DONE]':
                            break
                        try:
                            chunk_data = json.loads(data_str)
                            if 'choices' in chunk_data and len(chunk_data['choices']) > 0:
                                delta = chunk_data['choices'][0].get('delta', {})
                                content = delta.get('content')
                                if content:
                                    yield content
                        except json.JSONDecodeError:
                            continue
        except httpx.RequestError as e:
            logging.error(f"Erreur de requête streamée vers vLLM: {e}")
            yield "[ERREUR: Le service LLM est indisponible]"

    async def get_chat_completion(self, message_history, temperature: float, max_tokens: int, enable_thinking: bool) -> str:
        try:
            request_payload = {
                "model": MODEL_NAME,
                "messages": message_history,
                "stream": False,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "chat_template_kwargs": {"enable_thinking": enable_thinking}
            }
            # Utiliser la même instance partagée
            response = await self.http_client.post(VLLM_API_URL, json=request_payload)
            response.raise_for_status()
            response_data = response.json()
            if 'choices' in response_data and len(response_data['choices']) > 0:
                return response_data['choices'][0].get('message', {}).get('content', '')
            return "[ERREUR: Réponse inattendue du service LLM]"
        except httpx.TimeoutException:
            logging.error(f"Timeout dépassé lors de la requête non-streamée vers vLLM.")
            return "[ERREUR: La génération de la réponse a pris trop de temps]"
        except httpx.RequestError as e:
            logging.error(f"Erreur de requête non-streamée vers vLLM: {e}")
            return "[ERREUR: Le service LLM est indisponible]"

    async def close(self):
        """Méthode pour fermer proprement le client lors de l'arrêt de l'application."""
        await self.http_client.aclose()