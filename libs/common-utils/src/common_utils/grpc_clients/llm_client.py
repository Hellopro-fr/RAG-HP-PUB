import grpc
import os
import logging
import asyncio

from grpc_stubs import  llm_pb2
from grpc_stubs import  llm_pb2_grpc

from schemas.chat import ChatRequest

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
                    enable_thinking=data.enable_thinking
                )

            stream = stub.ChatStream(request_generator())
            async for response in stream:
                yield response.chunk
    except grpc.aio.AioRpcError as e:
        logging.error(f"Erreur gRPC en appelant le service LLM: {e.details()}")
        yield f"[ERREUR_API: {e.details()}]"

async def get_llm_chat_response(
    data: ChatRequest
) -> str:
    """
    Appelle le service gRPC LLM pour obtenir une réponse complète (non-streamée).
    """
    try:
        async with grpc.aio.insecure_channel(LLM_SERVICE_URL) as channel:
            stub = llm_pb2_grpc.LLMServiceStub(channel)
            request = llm_pb2.ChatRequest(
                message=data.prompt,
                temperature=data.temperature,
                max_tokens=data.max_tokens,
                enable_thinking=data.enable_thinking
            )
            response = await stub.Chat(request)
            return response.full_message
    except grpc.aio.AioRpcError as e:
        logging.error(f"Erreur gRPC en appelant le service LLM (non-streamé): {e.details()}")
        return f"[ERREUR_CLIENT: {e.details()}]"