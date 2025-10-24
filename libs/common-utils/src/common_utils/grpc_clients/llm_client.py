import grpc
import os
import logging
import asyncio
from typing import List, Dict
from google.protobuf.json_format import MessageToDict
from google.protobuf import struct_pb2

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
            
            # Create a Struct for the options
            options_struct = struct_pb2.Struct()
            if data.options:
                options_struct.update(data.options)

            # Crée un générateur asynchrone pour envoyer la requête initiale
            async def request_generator():
                yield llm_pb2.ChatRequest(
                    message=data.prompt,
                    temperature=data.temperature,
                    max_tokens=data.max_tokens,
                    enable_thinking=data.enable_thinking,
                    options=options_struct
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

            # Create a Struct for the options
            options_struct = struct_pb2.Struct()
            if data.options:
                options_struct.update(data.options)

            request = llm_pb2.ChatRequest(
                message=data.prompt,
                temperature=data.temperature,
                max_tokens=data.max_tokens,
                enable_thinking=data.enable_thinking,
                options=options_struct
            )
            response = await stub.Chat(request)
            
            # Convert the Protobuf Struct back to a Python dictionary
            return MessageToDict(response.full_message)

    except grpc.aio.AioRpcError as e:
        logging.error(f"Erreur gRPC en appelant le service LLM (non-streamé): {e.details()}")
        return {
            "full_message": f"[ERREUR_CLIENT: {e.details()}]",
            "response": {"error": e.details(), "type": "AioRpcError"}
        }
    
async def get_llm_chat_batch_response(messages: List[str], temperature: float, max_tokens: int, enable_thinking: bool, **kwargs) -> List[Dict]:
    """
    Appelle le service gRPC LLM pour obtenir des réponses complètes pour un lot de messages.
    """
    if not messages:
        return []
    try:
        async with grpc.aio.insecure_channel(LLM_SERVICE_URL) as channel:
            stub = llm_pb2_grpc.LLMServiceStub(channel)

            options_struct = struct_pb2.Struct()
            if "options" in kwargs and kwargs["options"]:
                options_struct.update(kwargs["options"])

            request = llm_pb2.ChatBatchRequest(
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                enable_thinking=enable_thinking,
                options=options_struct
            )
            response = await stub.ChatBatch(request)

            # Convert each Struct in the response to a Python dictionary
            return [MessageToDict(msg) for msg in response.full_messages]
    except grpc.aio.AioRpcError as e:
        logging.error(f"Erreur gRPC en appelant le service LLM (batch): {e.details()}")
        # Return a list of error dictionaries matching the expected structure
        error_response = {
            "full_message": f"[ERREUR_CLIENT: {e.details()}]",
            "response": {"error": e.details(), "type": "AioRpcError"}
        }
        return [error_response for _ in messages]