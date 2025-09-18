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
from app.schemas.chat import ChatRequest, chatResponse 


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# @lru_cache(maxsize=None)
async def get_chat_completion_response(request: ChatRequest):

    start_time = time.perf_counter()

    prompt = request.prompt

    # Appeler le service LLM via gRPC pour obtenir la réponse
    response = await llm_client.get_llm_chat_response(prompt)

    logger.info("LLM response received. \nResponse: %s", response)

    time_elapsed = time.perf_counter() - start_time
    logger.info(f"Temps écoulé pour get_next_questinon: {time_elapsed:.2f} secondes")

    return {"response": response , "time_elapsed": time_elapsed}


