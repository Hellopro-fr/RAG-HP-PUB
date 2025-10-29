import grpc
import os
import logging
from typing import List

from grpc_stubs import reranking_pb2
from grpc_stubs import reranking_pb2_grpc
from google.protobuf.json_format import MessageToDict

RERANKING_SERVICE_URL = os.getenv("RERANKING_SERVICE_URL", "reranking-model-service:50053")

async def rerank_documents(query: str, documents: List[str]) -> List[str]:
    """
    Appelle le service gRPC de reranking pour réorganiser une liste de documents.
    """
    if not documents:
        return []
    try:
        async with grpc.aio.insecure_channel(RERANKING_SERVICE_URL) as channel:
            stub = reranking_pb2_grpc.RerankingServiceStub(channel)
            request = reranking_pb2.RerankRequest(query=query, documents=documents)
            response = await stub.Rerank(request)
            return list(response.ranked_documents)
    except grpc.aio.AioRpcError as e:
        logging.error(f"Erreur gRPC en appelant le service Reranking: {e.details()}")
        # En cas d'erreur du reranker, on retourne les documents originaux pour ne pas bloquer la recherche
        return documents

async def rerank_documents_with_scores(query: str, documents: List[str]) -> List[Dict]:
    """
    Appelle le service gRPC de reranking pour réorganiser une liste de documents et retourne les scores.
    """
    if not documents:
        return []
    try:
        async with grpc.aio.insecure_channel(RERANKING_SERVICE_URL) as channel:
            stub = reranking_pb2_grpc.RerankingServiceStub(channel)
            request = reranking_pb2.RerankRequest(query=query, documents=documents)
            response = await stub.RerankDocuments(request)
            return [{'document': s.document, 'score': s.score} for s in response.scores]
    except grpc.aio.AioRpcError as e:
        logging.error(f"Erreur gRPC en appelant le service Reranking (avec scores): {e.details()}")
        # En cas d'erreur, retourner les documents originaux avec un score de 0.
        return [{'document': doc, 'score': 0.0} for doc in documents]