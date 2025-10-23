import re
import httpx
import json
import os
import logging
import asyncio

# L'URL est maintenant dynamique, lue depuis les variables d'environnement
INFERENCE_SERVER_URL = os.getenv("INFERENCE_SERVER_URL", "http://vllm-server:8000/v1/chat/completions")
MODEL_NAME = os.getenv("MODEL_NAME", "Qwen/Qwen3-14B-AWQ")
MAX_RETRIES = 3
INITIAL_BACKOFF_DELAY = 15  # seconds
ADDING_TIME = 30  # seconds

class InferenceClient:
    def __init__(self):
        # Créer une seule instance client avec un timeout généreux
        # et des limites de connexion pour la robustesse.
        timeout_config = httpx.Timeout(None, connect=10.0)
        limits_config = httpx.Limits(max_connections=100, max_keepalive_connections=20)
        self.http_client = httpx.AsyncClient(
            timeout=timeout_config, limits=limits_config
        )

    async def stream_chat(
        self,
        message_history,
        temperature: float,
        max_tokens: int,
        enable_thinking: bool,
        **kwargs,
    ):
        delay = INITIAL_BACKOFF_DELAY
        for attempt in range(MAX_RETRIES):
            try:
                async with httpx.AsyncClient(timeout=None) as client:
                    request_payload = {
                        "model": MODEL_NAME,
                        "messages": message_history,
                        "stream": True,
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                        "chat_template_kwargs": {"enable_thinking": enable_thinking},
                    }

                    if kwargs.get("options"):
                        for key, value in kwargs["options"].items():
                            request_payload[key] = value

                    async with client.stream(
                        "POST", INFERENCE_SERVER_URL, json=request_payload
                    ) as response:
                        response.raise_for_status()
                        async for line in response.aiter_lines():
                            if line.startswith("data: "):
                                data_str = line[len("data: ") :].strip()
                                if data_str == "[DONE]":
                                    break
                                try:
                                    chunk_data = json.loads(data_str)
                                    if (
                                        "choices" in chunk_data
                                        and len(chunk_data["choices"]) > 0
                                    ):
                                        delta = chunk_data["choices"][0].get(
                                            "delta", {}
                                        )
                                        content = delta.get("content")
                                        if content:
                                            yield content
                                except json.JSONDecodeError:
                                    continue
                        return  # Successful stream completion
            except httpx.RequestError as e:
                logging.warning(
                    f"Tentative {attempt + 1}/{MAX_RETRIES} échouée pour contacter le serveur d'inférence: {e}"
                )
                if attempt + 1 == MAX_RETRIES:
                    logging.error(
                        f"Échec final pour contacter le serveur d'inférence après {MAX_RETRIES} tentatives."
                    )
                    yield "[ERREUR: Le service LLM est indisponible après plusieurs tentatives]"
                    return
                await asyncio.sleep(delay)
                delay += ADDING_TIME
        yield "[ERREUR: Le service LLM est indisponible après plusieurs tentatives]"

    async def get_chat_completion(
        self,
        message_history,
        temperature: float,
        max_tokens: int,
        enable_thinking: bool,
        **kwargs,
    ) -> str:
        delay = INITIAL_BACKOFF_DELAY
        for attempt in range(MAX_RETRIES):
            try:
                timeout_config = httpx.Timeout(None)
                logging.info(f'INFERENCE_SERVER_URL : {INFERENCE_SERVER_URL}')
                async with httpx.AsyncClient(timeout=timeout_config) as client:
                    request_payload = {
                        "model": MODEL_NAME,
                        "messages": message_history,
                        "stream": False,
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                        "chat_template_kwargs": {"enable_thinking": enable_thinking},
                    }
                    if kwargs.get("options"):
                        for key, value in kwargs["options"].items():
                            request_payload[key] = value

                    # logging.info(f'request payload : {request_payload}')
                    response = await client.post(INFERENCE_SERVER_URL, json=request_payload)
                    response.raise_for_status()
                    response_data = response.json()
                    if "choices" in response_data and len(response_data["choices"]) > 0:
                        return re.sub(
                            r"\s+",
                            " ",
                            re.sub(
                                r"<think>.*?</think>",
                                "",
                                response_data["choices"][0]
                                .get("message", {})
                                .get("content", ""),
                                flags=re.DOTALL,
                            ),
                        ).strip()
                    return "[ERREUR: Réponse inattendue du service LLM]"
            except httpx.TimeoutException:
                logging.error(
                    f"Timeout dépassé lors de la requête non-streamée vers le serveur d'inférence."
                )
                return "[ERREUR: La génération de la réponse a pris trop de temps]"
            except httpx.RequestError as e:
                logging.warning(
                    f"Tentative {attempt + 1}/{MAX_RETRIES} échouée pour contacter le serveur d'inférence: {e}"
                )
                if attempt + 1 == MAX_RETRIES:
                    logging.error(
                        f"Échec final pour contacter le serveur d'inférence après {MAX_RETRIES} tentatives."
                    )
                    return "[ERREUR: Le service LLM est indisponible après plusieurs tentatives]"
                await asyncio.sleep(delay)
                delay += ADDING_TIME
        return "[ERREUR: Le service LLM est indisponible après plusieurs tentatives]"
