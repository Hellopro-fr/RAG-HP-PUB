import grpc
import os
import logging
import asyncio

import llm_pb2
import llm_pb2_grpc

LLM_SERVICE_URL = os.getenv("LLM_SERVICE_URL", "llm-service:50051")

async def stream_llm_chat(message: str):
    try:
        async with grpc.aio.insecure_channel(LLM_SERVICE_URL) as channel:
            stub = llm_pb2_grpc.LLMServiceStub(channel)
            
            # Crée un générateur asynchrone pour envoyer la requête initiale
            async def request_generator():
                yield llm_pb2.ChatRequest(message=message)

            stream = stub.ChatStream(request_generator())
            async for response in stream:
                yield response.chunk
    except grpc.aio.AioRpcError as e:
        logging.error(f"Erreur gRPC en appelant le service LLM: {e.details()}")
        yield f"[ERREUR_API: {e.details()}]"
