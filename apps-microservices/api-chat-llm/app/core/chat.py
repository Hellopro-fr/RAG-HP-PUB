from functools import lru_cache
import time
import logging
import asyncio
from typing import List
from unittest import result
from google.protobuf.json_format import MessageToDict

# Import des clients gRPC de notre architecture
from common_utils.grpc_clients import (
    llm_client,
)


# Import des schémas Pydantic (à adapter si les chemins ont changé)
from app.schemas.chat import chatResponse
from common_utils.grpc_clients.schemas.chat import ChatRequest
from app.core.credentials import settings
from openai import OpenAI, AsyncOpenAI


logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class DeepSeek:
    def __init__(self, config=None):
        config = config or {}
        self.API_KEY = config.get("api_key", settings.DEEPSEEK_API_KEY)
        self.BASE_URL = "https://api.deepseek.com"
        self.MODEL = "deepseek-chat"
        self.TEMPERATURE = 0.4
        self.client = OpenAI(api_key=self.API_KEY, base_url=self.BASE_URL)
        self.async_client = AsyncOpenAI(api_key=self.API_KEY, base_url=self.BASE_URL)

    def chat(self, message, stream=False):
        response = self.client.chat.completions.create(
            model=self.MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "Tu es un assistant intelligent et serviable.",
                },
                {"role": "user", "content": message},
            ],
            temperature=self.TEMPERATURE,
            stream=stream,
        )
        if stream:
            return response
        return {"content": response.choices[0].message.content, "response": response}

    def set_temperature(self, temperature):
        self.TEMPERATURE = float(temperature)
        
    async def stream(self, message):
        response_stream = await self.async_client.chat.completions.create(
            model=self.MODEL,
            messages=[
                {"role": "system", "content": "You are a helpful and intelligent assistant."},
                {"role": "user", "content": message},
            ],
            temperature=self.TEMPERATURE,
            stream=True
        )
        async for chunk in response_stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content


logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@lru_cache(maxsize=None)
def get_openai_client():
    logger.info("Initialisation du client OpenAI...")
    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    logger.info("Client OpenAI initialisé.")
    return client


# Chat completion via llm Qwen3 14B
async def llm_prompt_qwen(request: ChatRequest) -> str:
    # Appeler le service LLM via gRPC pour obtenir la réponse
    response = await llm_client.get_llm_chat_response(request)
    return response


async def get_chat_completion_response(request: ChatRequest):

    start_time = time.perf_counter()

    # appel chat en asyncio
    response = await llm_client.get_llm_chat_response(request)
    # response = await asyncio.to_thread(llm_client.get_llm_chat_response, request)

    # logger.info("LLM response received. \nResponse: %s", response)

    time_elapsed = time.perf_counter() - start_time
    logger.info(f"Temps écoulé pour get_next_questinon: {time_elapsed:.2f} secondes")

    return {
        "response": response.get("full_message", ""),
        "api_response": response.get("response", {}),
        "time_elapsed": time_elapsed,
    }


# Chat completion via chatGpt 40
def llm_prompt_chatgpt(request: ChatRequest) -> str:
    # Appel chat completion avec Chatgpt , model fixe pour l'instant
    openai_client = get_openai_client()
    tab_response = openai_client.chat.completions.create(
        model="gpt-4o-2024-11-20",
        messages=[{"role": "user", "content": request.prompt}],
        temperature=float(request.temperature),
        stream=False,
    )

    response = tab_response.choices[0].message.content

    tab_response_dict = (
        tab_response.model_dump()
        if hasattr(tab_response, "model_dump")
        else dict(tab_response)
    )

    return {"message": response, "api_response": tab_response_dict}


async def get_chatgpt_chat_completion_response(request: ChatRequest):

    start_time = time.perf_counter()

    # appel chat en asyncio
    response = await asyncio.to_thread(llm_prompt_chatgpt, request)

    # logger.info("ChatGPT response received. \nResponse: %s", response)

    time_elapsed = time.perf_counter() - start_time
    logger.info(f"Temps écoulé pour get_next_questinon: {time_elapsed:.2f} secondes")

    return {
        "response": response.get("message", ""),
        "api_response": response.get("api_response", {}),
        "time_elapsed": time_elapsed,
    }


# Chat completion via Deepseek
def llm_prompt_deepseek(request: ChatRequest) -> str:
    # Appel chat completion avec Deepseek
    deepseek = DeepSeek()
    deepseek.set_temperature(request.temperature)
    tab_response = deepseek.chat(request.prompt, stream=False)
    response = tab_response["content"]

    tab_response_dict = (
        tab_response.model_dump()
        if hasattr(tab_response, "model_dump")
        else dict(tab_response)
    )

    return {"message": response, "api_response": tab_response_dict}


async def get_deepseek_chat_completion_response(request: ChatRequest):

    start_time = time.perf_counter()

    # appel chat en asyncio
    response = await asyncio.to_thread(llm_prompt_deepseek, request)

    # logger.info("Deepseek response received. \nResponse: %s", response)

    time_elapsed = time.perf_counter() - start_time
    logger.info(f"Temps écoulé pour get_next_questinon: {time_elapsed:.2f} secondes")

    return {
        "response": response.get("message", ""),
        "api_response": response.get("api_response", {}),
        "time_elapsed": time_elapsed,
    }


# Chat completion via Gemini by openrouter
def llm_prompt_gemini(request: ChatRequest) -> str:
    # Appel chat completion avec openrouter de model genini flash 1.5
    client_or = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=settings.OPENROUTER_API_KEY,
    )
    completion = client_or.chat.completions.create(
        extra_body={},
        model="google/gemini-2.0-flash-001",
        messages=[
            {"role": "user", "content": [{"type": "text", "text": request.prompt}]}
        ],
    )
    response = completion.choices[0].message.content

    completion_dict = (
        completion.model_dump()
        if hasattr(completion, "model_dump")
        else completion.dict()
    )

    return {"message": response, "api_response": completion_dict}


async def get_gemini_chat_completion_response(request: ChatRequest):

    start_time = time.perf_counter()

    # appel chat en asyncio
    response = await asyncio.to_thread(llm_prompt_gemini, request)

    # logger.info("Deepseek response received. \nResponse: %s", response)

    time_elapsed = time.perf_counter() - start_time
    logger.info(f"Temps écoulé pour get_next_questinon: {time_elapsed:.2f} secondes")

    return {
        "response": response.get("message", ""),
        "api_response": response.get("api_response", {}),
        "time_elapsed": time_elapsed,
    }
