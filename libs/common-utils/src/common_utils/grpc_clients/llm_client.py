import grpc
import os
import logging
import asyncio
import json
from typing import List, Dict

from httpx import options

from grpc_stubs import  llm_pb2
from grpc_stubs import  llm_pb2_grpc

from common_utils.grpc_clients.schemas.chat import ChatRequest

LLM_SERVICE_URL = os.getenv("LLM_SERVICE_URL", "llm-service:50051")

async def stream_llm_chat(
    data: ChatRequest
):
    try:
        async with grpc.aio.insecure_channel(LLM_SERVICE_URL) as channel:
            stub = llm_pb2_grpc.LLMServiceStub(channel)
            
            # Crée un générateur asynchrone pour envoyer la requête initiale
            async def request_generator():
                yield llm_pb2.ChatRequest(
                    message=data.prompt,
                    temperature=data.temperature,
                    max_tokens=data.max_tokens,
                    enable_thinking=data.enable_thinking,
                    options=data.options
                )

            stream = stub.ChatStream(request_generator())
            async for response in stream:
                yield response.chunk
    except grpc.aio.AioRpcError as e:
        logging.error(f"Erreur gRPC en appelant le service LLM: {e.details()}")
        yield f"[ERREUR_API: {e.details()}]"

async def get_llm_chat_response(
    data: ChatRequest
) -> Dict:
    """
    Appelle le service gRPC LLM pour obtenir une réponse complète (non-streamée)
    et la parse en dictionnaire.
    """
    try:
        async with grpc.aio.insecure_channel(LLM_SERVICE_URL) as channel:
            stub = llm_pb2_grpc.LLMServiceStub(channel)
            request = llm_pb2.ChatRequest(
                message=data.prompt,
                temperature=data.temperature,
                max_tokens=data.max_tokens,
                enable_thinking=data.enable_thinking,
                options=data.options
            )
            response = await stub.Chat(request)
            try:
                # Désérialise la chaîne JSON reçue en dictionnaire Python
                return json.loads(response.full_message)
            except json.JSONDecodeError:
                logging.error(f"Erreur de décodage JSON de la réponse du LLM-service: {response.full_message}")
                return {
                    "full_message": "[ERREUR_CLIENT: Réponse JSON invalide du service LLM]",
                    "response": {"raw": response.full_message}
                }
    except grpc.aio.AioRpcError as e:
        logging.error(f"Erreur gRPC en appelant le service LLM (non-streamé): {e.details()}")
        return {
            "full_message": f"[ERREUR_CLIENT: {e.details()}]",
            "response": {"error": e.details(), "type": "AioRpcError"}
        }
    
async def get_llm_chat_batch_response(messages: List[str], temperature: float, max_tokens: int, enable_thinking: bool, **kwargs) -> List[str]:
    """
    Appelle le service gRPC LLM pour obtenir des réponses complètes pour un lot de messages.
    """
    if not messages:
        return []
    try:
        async with grpc.aio.insecure_channel(LLM_SERVICE_URL) as channel:
            stub = llm_pb2_grpc.LLMServiceStub(channel)
            request = llm_pb2.ChatBatchRequest(
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                enable_thinking=enable_thinking,
                options=kwargs.get("options", {})
            )
            response = await stub.ChatBatch(request)
            return list(response.full_messages)
    except grpc.aio.AioRpcError as e:
        logging.error(f"Erreur gRPC en appelant le service LLM (batch): {e.details()}")
        return [f"[ERREUR_CLIENT: {e.details()}]" for _ in messages]