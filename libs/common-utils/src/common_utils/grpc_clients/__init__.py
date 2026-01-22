# gRPC Clients
# Centralized gRPC clients for Graph RAG services

# Existing clients
from common_utils.grpc_clients import database_client
from common_utils.grpc_clients import embedding_client
from common_utils.grpc_clients import llm_client
from common_utils.grpc_clients import reranking_client

# New Graph RAG clients
from common_utils.grpc_clients import spacy_client
from common_utils.grpc_clients import graph_database_client
from common_utils.grpc_clients import graph_milvus_client
from common_utils.grpc_clients import graph_normalization_client

__all__ = [
    # Existing clients
    "database_client",
    "embedding_client",
    "llm_client",
    "reranking_client",
    # New Graph RAG clients
    "spacy_client",
    "graph_database_client",
    "graph_milvus_client",
    "graph_normalization_client",
]
