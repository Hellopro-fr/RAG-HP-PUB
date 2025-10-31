import grpc
import os
import logging
from typing import List, Optional

from grpc_stubs import database_pb2
from grpc_stubs import database_pb2_grpc

DATABASE_SERVICE_URL = os.getenv("DATABASE_SERVICE_URL", "database-recherche-service:50054")

# MODIFIÉ: La signature est mise à jour pour inclure les nouveaux paramètres optionnels
async def search_vector(
    collection: str, 
    vector: List[float], 
    k: int,
    filter_expr: Optional[str] = None,
    **kwargs
):
    try:
        async with grpc.aio.insecure_channel(DATABASE_SERVICE_URL) as channel:
            stub = database_pb2_grpc.DatabaseSearchServiceStub(channel)
            
            # MODIFIÉ: Construction de la requête avec les champs optionnels
            request = database_pb2.SearchRequest(
                collection_name=collection,
                query_embedding=vector,
                top_k=k
            )
            if filter_expr:
                request.filter_expression = filter_expr
            if kwargs.get("output_fields") and isinstance(kwargs.get("output_fields"), list):
                request.output_fields.extend(kwargs.get("output_fields", []))

            response = await stub.Search(request)
            return response.results
    except grpc.aio.AioRpcError as e:
        logging.error(f"Erreur gRPC en appelant le service Database: {e.details()}")
        return None
    
async def get_collection_schema(
    collection_name: str
) -> Optional[dict]:
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
    collection: str,
    filter_expr: str,
    k: int,
    output_fields: Optional[List[str]] = None
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
                output_fields=output_fields if output_fields else []
            )
            
            response = await stub.ClassicSearch(request)
            return response.results
    except grpc.aio.AioRpcError as e:
        logging.error(f"Erreur gRPC en appelant ClassicSearch: {e.details()}")
        return None