import re
import httpx
import json
import os
import logging
import asyncio

VLLM_API_URL = os.getenv("VLLM_API_URL", "http://vllm-server:8000/v1/chat/completions")
MODEL_NAME = os.getenv("MODEL_NAME", "Qwen/Qwen3-14B-AWQ")
MAX_RETRIES = 3
INITIAL_BACKOFF_DELAY = 15  # seconds
ADDING_TIME = 30  # seconds


class VLLMClient:
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
                    else:
                        request_payload["top_p"] = float(0.8)
                        request_payload["top_k"] = int(20)
                        request_payload["repetition_penalty"] = float(1.0)
                    async with client.stream(
                        "POST", VLLM_API_URL, json=request_payload
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
                    f"Tentative {attempt + 1}/{MAX_RETRIES} échouée pour contacter vLLM (stream): {e}"
                )
                if attempt + 1 == MAX_RETRIES:
                    logging.error(
                        f"Échec final pour contacter vLLM (stream) après {MAX_RETRIES} tentatives."
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
                    else:
                        request_payload["top_p"] = float(0.8)
                        request_payload["top_k"] = int(20)
                        request_payload["repetition_penalty"] = float(1.0)
                    response = await client.post(VLLM_API_URL, json=request_payload)
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
                    f"Timeout dépassé lors de la requête non-streamée vers vLLM."
                )
                return "[ERREUR: La génération de la réponse a pris trop de temps]"
            except httpx.RequestError as e:
                logging.warning(
                    f"Tentative {attempt + 1}/{MAX_RETRIES} échouée pour contacter vLLM: {e}"
                )
                if attempt + 1 == MAX_RETRIES:
                    logging.error(
                        f"Échec final pour contacter vLLM après {MAX_RETRIES} tentatives."
                    )
                    return "[ERREUR: Le service LLM est indisponible après plusieurs tentatives]"
                await asyncio.sleep(delay)
                delay += ADDING_TIME
        return "[ERREUR: Le service LLM est indisponible après plusieurs tentatives]"
