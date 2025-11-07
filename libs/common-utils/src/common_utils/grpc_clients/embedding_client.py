import grpc
import os
import logging
from typing import List

from grpc_stubs import  embedding_pb2
from grpc_stubs import  embedding_pb2_grpc

EMBEDDING_SERVICE_URL = os.getenv("EMBEDDING_SERVICE_URL", "embedding-model-service:50052")

# MODIFIÉ: La fonction est renommée et prend une liste de textes.
async def get_embeddings(texts: List[str]) -> List[List[float]]:
    """
    Appelle le service gRPC pour obtenir les embeddings pour une liste de textes.
    """
    if not texts:
        return []
    try:
        async with grpc.aio.insecure_channel(EMBEDDING_SERVICE_URL) as channel:
            stub = embedding_pb2_grpc.EmbeddingServiceStub(channel)
            # Utilise la nouvelle méthode RPC et le nouveau message de requête
            request = embedding_pb2.EmbeddingsRequest(texts=texts)
            response = await stub.GetEmbeddings(request)
            # Déballe la liste de messages EmbeddingVector en une liste de listes de floats
            return [list(e.vector) for e in response.embeddings]
    except grpc.aio.AioRpcError as e:
        logging.error(f"Erreur gRPC en appelant le service Embedding: {e.details()}")
        # MODIFIÉ: L'exception est propagée pour permettre au service appelant de gérer les reintentions.
        raise e

# Gardons l'ancienne fonction pour la compatibilité avec /database/search
# qui n'a besoin que d'un seul embedding à la fois.
# Elle est maintenant un simple wrapper autour de la nouvelle fonction de batching.
async def get_embedding(text: str) -> List[float]:
    """
    Obtient l'embedding pour un seul texte.
    Wrapper pour la fonction de batching.
    """
    results = await get_embeddings([text])
    return results[0] if results else []

async def tokenize(texts: List[str]) -> List[List[int]]:
    """
    Appelle le service gRPC pour tokenizer une liste de textes.
    """
    if not texts:
        return []
    try:
        async with grpc.aio.insecure_channel(EMBEDDING_SERVICE_URL) as channel:
            stub = embedding_pb2_grpc.EmbeddingServiceStub(channel)
            request = embedding_pb2.TokenizeRequest(texts=texts)
            response = await stub.Tokenize(request)
            return [list(t.tokens) for t in response.tokenized_texts]
    except grpc.aio.AioRpcError as e:
        logging.error(f"Erreur gRPC en appelant le service de Tokenization: {e.details()}")
        return [[] for _ in texts]
    
async def detokenize(token_lists: List[List[int]]) -> List[str]:
    """
    Appelle le service gRPC pour détokenizer une liste de listes de tokens.
    """
    if not token_lists:
        return []
    try:
        async with grpc.aio.insecure_channel(EMBEDDING_SERVICE_URL) as channel:
            stub = embedding_pb2_grpc.EmbeddingServiceStub(channel)
            # On reconstruit le message de requête
            tokenized_outputs = [embedding_pb2.TokenizedOutput(tokens=tokens) for tokens in token_lists]
            request = embedding_pb2.DetokenizeRequest(tokenized_texts=tokenized_outputs)
            
            response = await stub.Detokenize(request)
            return list(response.texts)
    except grpc.aio.AioRpcError as e:
        logging.error(f"Erreur gRPC en appelant le service de Detokenization: {e.details()}")
        return ["" for _ in token_lists]
    

async def chunk_text(text: str, chunk_size: int, chunk_overlap: int) -> List[str]:
    """
    Appelle le service gRPC pour découper un texte en chunks.
    """
    if not text:
        return []
    try:
        async with grpc.aio.insecure_channel(EMBEDDING_SERVICE_URL) as channel:
            stub = embedding_pb2_grpc.EmbeddingServiceStub(channel)
            request = embedding_pb2.ChunkRequest(
                text=text,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap
            )
            response = await stub.ChunkText(request)
            return list(response.chunks)
    except grpc.aio.AioRpcError as e:
        logging.error(f"Erreur gRPC en appelant le service de Chunking: {e.details()}")
        return []