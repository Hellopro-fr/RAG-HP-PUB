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
        return []

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