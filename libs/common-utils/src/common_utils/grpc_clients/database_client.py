import grpc
import os
import logging
from typing import List, Optional

from google.protobuf import struct_pb2

from grpc_stubs import database_pb2
from grpc_stubs import database_pb2_grpc

DATABASE_SERVICE_URL = os.getenv(
    "DATABASE_SERVICE_URL", "database-recherche-service:50054"
)


# MODIFIÉ: La signature est mise à jour pour inclure les nouveaux paramètres optionnels
async def search_vector(
    collection: str,
    vector: List[float],
    k: int,
    filter_expr: Optional[str] = None,
    **kwargs,
):
    try:
        async with grpc.aio.insecure_channel(DATABASE_SERVICE_URL) as channel:
            stub = database_pb2_grpc.DatabaseSearchServiceStub(channel)

            # MODIFIÉ: Construction de la requête avec les champs optionnels
            request = database_pb2.SearchRequest(
                collection_name=collection, query_embedding=vector, top_k=k
            )
            if filter_expr:
                request.filter_expression = filter_expr
            if kwargs.get("output_fields") and isinstance(
                kwargs.get("output_fields"), list
            ):
                request.output_fields.extend(kwargs.get("output_fields", []))
            if "context_mode" in kwargs:
                options_struct = struct_pb2.Struct()
                options_struct.update(
                    {"context_mode": kwargs.get("context_mode", None)}
                )
                request.options = options_struct

            response = await stub.Search(request)
            return response.results
    except grpc.aio.AioRpcError as e:
        logging.error(f"Erreur gRPC en appelant le service Database: {e.details()}")
        return None


async def get_collection_schema(collection_name: str) -> Optional[dict]:
    """
    Appelle le service gRPC pour obtenir le schéma d'une collection.
    """
    try:
        async with grpc.aio.insecure_channel(DATABASE_SERVICE_URL) as channel:
            stub = database_pb2_grpc.DatabaseSearchServiceStub(channel)
            request = database_pb2.GetSchemaRequest(collection_name=collection_name)
            response = await stub.GetSchema(request)
            return dict(response.fields)
    except grpc.aio.AioRpcError as e:
        logging.error(f"Erreur gRPC en appelant GetSchema: {e.details()}")
        return None


async def classic_search_vector(
    collection: str, filter_expr: str, k: int, output_fields: Optional[List[str]] = None
):
    """
    Appelle le service gRPC pour effectuer une recherche classique par filtre.
    """
    try:
        async with grpc.aio.insecure_channel(DATABASE_SERVICE_URL) as channel:
            stub = database_pb2_grpc.DatabaseSearchServiceStub(channel)

            request = database_pb2.ClassicSearchRequest(
                collection_name=collection,
                filter_expression=filter_expr,
                top_k=k,
                output_fields=output_fields if output_fields else [],
            )

            response = await stub.ClassicSearch(request)
            return response.results
    except grpc.aio.AioRpcError as e:
        logging.error(f"Erreur gRPC en appelant ClassicSearch: {e.details()}")
        return None


async def hybrid_search_vector(
    collection: str,
    dense_vector: List[float],
    query_text: str,
    k: int,
    dense_weight: float = 0.7,
    sparse_weight: float = 0.3,
    filter_expr: Optional[str] = None,
    # --- Paramètres d'exploration pour optimiser la pertinence ---
    ef: Optional[int] = None,
    radius: Optional[float] = None,
    range_filter: Optional[float] = None,
    drop_ratio_search: float = 0.0,
    dense_limit_multiplier: int = 1,
    ranker_type: str = "weighted",
    rrf_k: int = 60,
    **kwargs,
):
    """
    Appelle le service gRPC pour effectuer une recherche hybride
    combinant recherche vectorielle dense et recherche full-text BM25.

    Paramètres d'exploration (passés via le Struct 'options' du proto):
    - ef: largeur d'exploration HNSW (None=auto, 2000+=meilleur rappel)
    - radius: seuil de similarité minimum (COSINE)
    - range_filter: seuil de similarité maximum (COSINE)
    - drop_ratio_search: proportion de termes BM25 faibles à ignorer (0.0=max précision)
    - dense_limit_multiplier: facteur de sur-récupération par sous-requête
    - ranker_type: "weighted" ou "rrf" (Reciprocal Rank Fusion)
    - rrf_k: constante de lissage RRF (10-100)
    """
    try:
        async with grpc.aio.insecure_channel(DATABASE_SERVICE_URL) as channel:
            stub = database_pb2_grpc.DatabaseSearchServiceStub(channel)

            request = database_pb2.HybridSearchRequest(
                collection_name=collection,
                dense_vector=dense_vector,
                query_text=query_text,
                top_k=k,
                dense_weight=dense_weight,
                sparse_weight=sparse_weight,
            )
            if filter_expr:
                request.filter_expression = filter_expr
            if kwargs.get("output_fields") and isinstance(
                kwargs.get("output_fields"), list
            ):
                request.output_fields.extend(kwargs.get("output_fields", []))

            # Construction du Struct options avec les paramètres d'exploration
            options_data = {}
            if "context_mode" in kwargs:
                options_data["context_mode"] = kwargs.get("context_mode", None)
            if ef is not None:
                options_data["ef"] = ef
            if radius is not None:
                options_data["radius"] = radius
            if range_filter is not None:
                options_data["range_filter"] = range_filter
            if drop_ratio_search != 0.0:
                options_data["drop_ratio_search"] = drop_ratio_search
            if dense_limit_multiplier != 1:
                options_data["dense_limit_multiplier"] = dense_limit_multiplier
            if ranker_type != "weighted":
                options_data["ranker_type"] = ranker_type
            if rrf_k != 60:
                options_data["rrf_k"] = rrf_k

            if options_data:
                options_struct = struct_pb2.Struct()
                options_struct.update(options_data)
                request.options = options_struct

            response = await stub.HybridSearch(request)
            return response.results
    except grpc.aio.AioRpcError as e:
        logging.error(f"Erreur gRPC en appelant HybridSearch: {e.details()}")
        return None
