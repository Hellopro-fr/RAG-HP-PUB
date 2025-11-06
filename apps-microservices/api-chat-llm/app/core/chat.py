from functools import lru_cache
import time
import logging
import asyncio
from typing import Dict, List, Any, Optional
from unittest import result
from google.protobuf.json_format import MessageToDict

# Import des clients gRPC de notre architecture
from common_utils.grpc_clients import (
    llm_client,
)


# Import des schémas Pydantic (à adapter si les chemins ont changé)
from app.schemas.chat import chatResponse, BatchChatRequest,BatchResult , BatchRequestInput
from common_utils.grpc_clients.schemas.chat import ChatRequest
from app.core.credentials import settings
from openai import OpenAI, AsyncOpenAI

from common_utils.grpc_clients.schemas.chat import ChatBaseURL, ChatProvider


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
            yield chunk




class LLMProvider:
    def __init__(self, config=None):
        config = config or {}
        self.PROVIDER = config.get("provider", ChatProvider.DEEPSEEK)
        if self.PROVIDER == ChatProvider.DEEPSEEK:
            self.API_KEY = config.get("api_key", settings.DEEPSEEK_API_KEY)
            self.BASE_URL = ChatBaseURL.DEEPSEEK
        elif self.PROVIDER == ChatProvider.GPT:
            self.API_KEY = config.get("api_key", settings.OPENAI_API_KEY)
            self.BASE_URL = ChatBaseURL.OPENAI
        elif self.PROVIDER == ChatProvider.OPENROUTER:
            self.API_KEY = config.get("api_key", settings.OPENROUTER_API_KEY)
            self.BASE_URL = ChatBaseURL.OPENROUTER

        self.MODEL = config.get("model","deepseek-chat")
        self.TEMPERATURE = config.get("temperature", 0.4)
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
            yield chunk

class ChatGPT:
    def __init__(self, config=None):
        config = config or {}
        self.API_KEY = config.get("api_key", settings.OPENAI_API_KEY)
        self.MODEL = config.get("model","gpt-4o-2024-11-20")
        self.TEMPERATURE = config.get("temperature", 0.4)
        self.client = OpenAI(api_key=self.API_KEY)
        self.async_client = AsyncOpenAI(api_key=self.API_KEY)

    def chat(self, message, stream=False):
        response = self.client.chat.completions.create(
            model=self.MODEL,
            messages=[
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
                {"role": "user", "content": message},
            ],
            temperature=self.TEMPERATURE,
            stream=True
        )
        async for chunk in response_stream:
            yield chunk
            
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


class OpenRouter:
    def __init__(self, config=None):
        config = config or {}
        self.API_KEY = config.get("api_key", settings.OPENROUTER_API_KEY)
        self.BASE_URL = "https://openrouter.ai/api/v1"
        self.MODEL = config.get("model", "qwen/qwen3-coder")
        self.TEMPERATURE = config.get("temperature", 0.4)
        self.client = OpenAI(api_key=self.API_KEY, base_url=self.BASE_URL)
        self.async_client = AsyncOpenAI(api_key=self.API_KEY, base_url=self.BASE_URL)

    def chat(self, message, stream=False):
        response = self.client.chat.completions.create(
            extra_body={},
            model=self.MODEL,
            messages=[
                {"role": "user", "content": [{"type": "text", "text": message}]}
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
            extra_body={},
            model=self.MODEL,
            messages=[
                {"role": "user", "content": [{"type": "text", "text": message}]}
            ],
            temperature=self.TEMPERATURE,
            stream=True
        )
        async for chunk in response_stream:
            yield chunk

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
    openrouter_client = OpenRouter()
    openrouter_client.set_temperature(request.temperature)
    completion = openrouter_client.chat(request.prompt, stream=False)
    response = completion["content"]

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

# Chat completion via Deepseek
async def llm_prompt_batch_deepseek(requestInput: BatchRequestInput, max_tokens: int = 1024 , enable_thinking: bool = False , temperature: float = 0.7) -> BatchResult:

    start_time = time.perf_counter()
   

    # appel chat en asyncio
    
    response = await asyncio.to_thread(llm_prompt_deepseek, ChatRequest(
        prompt=requestInput.prompt,
        temperature=temperature,
        max_tokens=max_tokens,
        enable_thinking=enable_thinking
    ))

    time_elapsed = time.perf_counter() - start_time

    return BatchResult(
        id_request=requestInput.id_request, 
        llm_response=response.get("api_response", {}), 
        time_elapsed=time_elapsed
    )

async def get_batch_deepseek_chat_completion_response(BatchRequest: BatchChatRequest):

    start_time = time.perf_counter()

    # Créer une tâche asynchrone pour chaque produit
    tasks = [
        llm_prompt_batch_deepseek(requestInput, max_tokens=BatchRequest.max_tokens, enable_thinking=BatchRequest.enable_thinking , temperature=BatchRequest.temperature)
        for requestInput in BatchRequest.list_request
    ]

    # Exécuter toutes les tâches en parallèle et attendre leurs résultats
    results = await asyncio.gather(*tasks)

    # Vérifier si asyncio.gather a retourné des exceptions
    processed_results = []
    for res in results:
        if isinstance(res, Exception):
            logger.error(f"Une tâche a échoué dans le batch: {res}")
            # Vous pouvez décider quoi faire ici, par exemple retourner un objet d'erreur
            processed_results.append(BatchResult(id_request="unknown_error", llm_response={"error": str(res)}))
        else:
            processed_results.append(res)

    time_elapsed = time.perf_counter() - start_time

    return {
        "resultats": processed_results,
        "all_time_elapsed": time_elapsed,
    }