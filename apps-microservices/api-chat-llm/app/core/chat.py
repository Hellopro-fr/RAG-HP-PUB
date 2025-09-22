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
from app.schemas.chat import  chatResponse 
from common_utils.grpc_clients.schemas.chat import ChatRequest
from openai import OpenAI

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class DeepSeek:
	def __init__(self, config=None):
		config = config or {}
		self.API_KEY = config.get("api_key", settings.DEEPSEEK_API_KEY)
		self.BASE_URL = "https://api.deepseek.com"
		self.MODEL = "deepseek-chat"
		self.TEMPERATURE = 0.4
		self.client = OpenAI(api_key=self.API_KEY, base_url=self.BASE_URL)

	def chat(self, message, stream=False):
		response = self.client.chat.completions.create(
			model=self.MODEL,
			messages=[
				{"role": "system", "content": "Tu es un assistant intelligent et serviable."},
				{"role": "user", "content": message},
			],
			temperature=self.TEMPERATURE,
			stream=stream
		)
		if stream:
			return response
		return {"content": response.choices[0].message.content, "response": response}

	def set_temperature(self, temperature):
		self.TEMPERATURE = float(temperature)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@lru_cache(maxsize=None)
def get_openai_client():
    logger.info("Initialisation du client OpenAI...")
    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    logger.info("Client OpenAI initialisé.")
    return client

async def get_chat_completion_response(request: ChatRequest):

    start_time = time.perf_counter()

    # Appeler le service LLM via gRPC pour obtenir la réponse
    response = await llm_client.get_llm_chat_response(request)

    logger.info("LLM response received. \nResponse: %s", response)

    time_elapsed = time.perf_counter() - start_time
    logger.info(f"Temps écoulé pour get_next_questinon: {time_elapsed:.2f} secondes")

    return {"response": response , "time_elapsed": time_elapsed}


async def get_chatgpt_chat_completion_response(request: ChatRequest):

    start_time = time.perf_counter()

    # Appel chat completion avec Chatgpt , model fixe pour l'instant
    openai_client = get_openai_client()
    response = openai_client.chat.completions.create(
        model="gpt-4.1-2025-04-14",
        messages=[{"role": "user", "content": request.prompt}],
        temperature=float(request.temperature),
        stream=False
    )

    logger.info("ChatGPT response received. \nResponse: %s", response)

    time_elapsed = time.perf_counter() - start_time
    logger.info(f"Temps écoulé pour get_next_questinon: {time_elapsed:.2f} secondes")

    return {"response": response , "time_elapsed": time_elapsed}

async def get_deepseek_chat_completion_response(request: ChatRequest):

    start_time = time.perf_counter()

    # Appel chat completion avec Deepseek
    deepseek = DeepSeek()
    deepseek.set_temperature(request.temperature)
    response = deepseek.chat(request.prompt , stream=False)

    logger.info("Deepseek response received. \nResponse: %s", response)

    time_elapsed = time.perf_counter() - start_time
    logger.info(f"Temps écoulé pour get_next_questinon: {time_elapsed:.2f} secondes")

    return {"response": response , "time_elapsed": time_elapsed}