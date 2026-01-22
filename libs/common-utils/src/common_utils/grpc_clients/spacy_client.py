import grpc
import os
import logging
from typing import List, Optional
from dataclasses import dataclass

from grpc_stubs import spacy_pb2
from grpc_stubs import spacy_pb2_grpc

SPACY_SERVICE_URL = os.getenv("SPACY_SERVICE_URL", "graph-rag-spacy-service:50051")


@dataclass
class Token:
    """Token with lemmatization information."""
    text: str
    lemma: str
    pos: str
    is_stop: bool


@dataclass
class Entity:
    """Named entity extracted from text."""
    text: str
    label: str
    start_char: int
    end_char: int


async def lemmatize(text: str) -> List[Token]:
    """
    Call the gRPC service to lemmatize text.
    
    Args:
        text: The text to lemmatize.
        
    Returns:
        List of Token objects with lemma, POS, and stop word information.
    """
    if not text:
        return []
    try:
        async with grpc.aio.insecure_channel(SPACY_SERVICE_URL) as channel:
            stub = spacy_pb2_grpc.GraphSpacyServiceStub(channel)
            request = spacy_pb2.LemmatizeRequest(text=text)
            response = await stub.Lemmatize(request)
            return [
                Token(
                    text=token.text,
                    lemma=token.lemma,
                    pos=token.pos,
                    is_stop=token.is_stop
                )
                for token in response.tokens
            ]
    except grpc.aio.AioRpcError as e:
        logging.error(f"gRPC error calling Spacy Lemmatize: {e.details()}")
        raise e


async def extract_entities(text: str) -> List[Entity]:
    """
    Call the gRPC service to extract named entities from text.
    
    Args:
        text: The text to analyze for entities.
        
    Returns:
        List of Entity objects with text, label, and character positions.
    """
    if not text:
        return []
    try:
        async with grpc.aio.insecure_channel(SPACY_SERVICE_URL) as channel:
            stub = spacy_pb2_grpc.GraphSpacyServiceStub(channel)
            request = spacy_pb2.ExtractEntitiesRequest(text=text)
            response = await stub.ExtractEntities(request)
            return [
                Entity(
                    text=entity.text,
                    label=entity.label,
                    start_char=entity.start_char,
                    end_char=entity.end_char
                )
                for entity in response.entities
            ]
    except grpc.aio.AioRpcError as e:
        logging.error(f"gRPC error calling Spacy ExtractEntities: {e.details()}")
        raise e
