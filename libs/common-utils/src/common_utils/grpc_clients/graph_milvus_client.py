import grpc
import os
import logging
from typing import List, Tuple, Optional
from dataclasses import dataclass

from grpc_stubs import graph_milvus_pb2
from grpc_stubs import graph_milvus_pb2_grpc

MILVUS_SERVICE_URL = os.getenv("MILVUS_SERVICE_URL", "graph-rag-milvus-service:50051")


@dataclass
class SearchResult:
    """Search result from Milvus."""
    id: str
    distance: float
    label: str = ""


# =============================================================================
# Entity Operations
# =============================================================================

async def upsert_entity(
    id: str,
    entity_type: str,
    embedding: List[float]
) -> Tuple[bool, str]:
    """
    Upsert a single canonical entity.
    
    Args:
        id: Unique identifier for the entity.
        entity_type: Type of entity (e.g., 'Produit', 'Fournisseur').
        embedding: Vector embedding for the entity.
        
    Returns:
        Tuple of (success, error_message).
    """
    try:
        async with grpc.aio.insecure_channel(MILVUS_SERVICE_URL) as channel:
            stub = graph_milvus_pb2_grpc.GraphMilvusServiceStub(channel)
            request = graph_milvus_pb2.UpsertEntityRequest(
                id=id,
                entity_type=entity_type,
                embedding=embedding
            )
            response = await stub.UpsertCanonicalEntity(request)
            return response.success, response.error_message
    except grpc.aio.AioRpcError as e:
        logging.error(f"gRPC error upserting entity: {e.details()}")
        raise e


async def upsert_entity_batch(
    entities: List[dict]
) -> Tuple[bool, str, int]:
    """
    Upsert multiple entities in a batch.
    
    Args:
        entities: List of dicts with 'id', 'entity_type', and 'embedding' keys.
        
    Returns:
        Tuple of (success, error_message, inserted_count).
    """
    try:
        async with grpc.aio.insecure_channel(MILVUS_SERVICE_URL) as channel:
            stub = graph_milvus_pb2_grpc.GraphMilvusServiceStub(channel)
            
            entity_items = [
                graph_milvus_pb2.EntityItem(
                    id=e["id"],
                    entity_type=e["entity_type"],
                    embedding=e["embedding"]
                )
                for e in entities
            ]
            
            request = graph_milvus_pb2.UpsertEntityBatchRequest(entities=entity_items)
            response = await stub.UpsertEntityBatch(request)
            return response.success, response.error_message, response.inserted_count
    except grpc.aio.AioRpcError as e:
        logging.error(f"gRPC error upserting entity batch: {e.details()}")
        raise e


async def search_similar_entities(
    embedding: List[float],
    entity_type: str,
    top_k: int = 5,
    threshold: float = 0.8
) -> List[SearchResult]:
    """
    Search for similar entities.
    
    Args:
        embedding: Query vector embedding.
        entity_type: Type of entity to search for.
        top_k: Maximum number of results.
        threshold: Similarity threshold (0.0 - 1.0).
        
    Returns:
        List of SearchResult objects.
    """
    try:
        async with grpc.aio.insecure_channel(MILVUS_SERVICE_URL) as channel:
            stub = graph_milvus_pb2_grpc.GraphMilvusServiceStub(channel)
            request = graph_milvus_pb2.SearchEntitiesRequest(
                embedding=embedding,
                entity_type=entity_type,
                top_k=top_k,
                threshold=threshold
            )
            response = await stub.SearchSimilarEntities(request)
            return [
                SearchResult(id=r.id, distance=r.distance, label=r.label)
                for r in response.results
            ]
    except grpc.aio.AioRpcError as e:
        logging.error(f"gRPC error searching entities: {e.details()}")
        raise e


async def check_entities_exist(ids: List[str]) -> List[str]:
    """
    Check which entity IDs already exist in Milvus.
    
    Args:
        ids: List of entity IDs to check.
        
    Returns:
        List of existing entity IDs.
    """
    try:
        async with grpc.aio.insecure_channel(MILVUS_SERVICE_URL) as channel:
            stub = graph_milvus_pb2_grpc.GraphMilvusServiceStub(channel)
            request = graph_milvus_pb2.CheckExistRequest(ids=ids)
            response = await stub.CheckEntitiesExist(request)
            return list(response.existing_ids)
    except grpc.aio.AioRpcError as e:
        logging.error(f"gRPC error checking entities exist: {e.details()}")
        raise e


# =============================================================================
# Label Operations
# =============================================================================

async def upsert_label(
    label: str,
    embedding: List[float]
) -> Tuple[bool, str]:
    """
    Upsert a single canonical label.
    
    Args:
        label: The canonical label text.
        embedding: Vector embedding for the label.
        
    Returns:
        Tuple of (success, error_message).
    """
    try:
        async with grpc.aio.insecure_channel(MILVUS_SERVICE_URL) as channel:
            stub = graph_milvus_pb2_grpc.GraphMilvusServiceStub(channel)
            request = graph_milvus_pb2.UpsertLabelRequest(
                label=label,
                embedding=embedding
            )
            response = await stub.UpsertCanonicalLabel(request)
            return response.success, response.error_message
    except grpc.aio.AioRpcError as e:
        logging.error(f"gRPC error upserting label: {e.details()}")
        raise e


async def upsert_label_batch(
    labels: List[dict]
) -> Tuple[bool, str, int]:
    """
    Upsert multiple labels in a batch.
    
    Args:
        labels: List of dicts with 'label' and 'embedding' keys.
        
    Returns:
        Tuple of (success, error_message, inserted_count).
    """
    try:
        async with grpc.aio.insecure_channel(MILVUS_SERVICE_URL) as channel:
            stub = graph_milvus_pb2_grpc.GraphMilvusServiceStub(channel)
            
            label_items = [
                graph_milvus_pb2.LabelItem(
                    label=l["label"],
                    embedding=l["embedding"]
                )
                for l in labels
            ]
            
            request = graph_milvus_pb2.UpsertLabelBatchRequest(labels=label_items)
            response = await stub.UpsertLabelBatch(request)
            return response.success, response.error_message, response.inserted_count
    except grpc.aio.AioRpcError as e:
        logging.error(f"gRPC error upserting label batch: {e.details()}")
        raise e


async def search_similar_labels(
    embedding: List[float],
    top_k: int = 1,
    threshold: float = 0.9
) -> List[SearchResult]:
    """
    Search for similar labels.
    
    Args:
        embedding: Query vector embedding.
        top_k: Maximum number of results.
        threshold: Similarity threshold (0.0 - 1.0).
        
    Returns:
        List of SearchResult objects.
    """
    try:
        async with grpc.aio.insecure_channel(MILVUS_SERVICE_URL) as channel:
            stub = graph_milvus_pb2_grpc.GraphMilvusServiceStub(channel)
            request = graph_milvus_pb2.SearchLabelsRequest(
                embedding=embedding,
                top_k=top_k,
                threshold=threshold
            )
            response = await stub.SearchSimilarLabels(request)
            return [
                SearchResult(id=r.id, distance=r.distance, label=r.label)
                for r in response.results
            ]
    except grpc.aio.AioRpcError as e:
        logging.error(f"gRPC error searching labels: {e.details()}")
        raise e


async def check_labels_exist(labels: List[str]) -> List[str]:
    """
    Check which labels already exist in Milvus.
    
    Args:
        labels: List of label strings to check.
        
    Returns:
        List of existing labels.
    """
    try:
        async with grpc.aio.insecure_channel(MILVUS_SERVICE_URL) as channel:
            stub = graph_milvus_pb2_grpc.GraphMilvusServiceStub(channel)
            request = graph_milvus_pb2.CheckLabelsExistRequest(labels=labels)
            response = await stub.CheckLabelsExist(request)
            return list(response.existing_labels)
    except grpc.aio.AioRpcError as e:
        logging.error(f"gRPC error checking labels exist: {e.details()}")
        raise e


# =============================================================================
# Characteristic Operations
# =============================================================================

async def upsert_characteristic(
    id: str,
    text: str,
    label_id: str,
    embedding: List[float]
) -> Tuple[bool, str]:
    """
    Upsert a single characteristic.
    
    Args:
        id: Unique identifier for the characteristic.
        text: The characteristic text/value.
        label_id: ID of the associated label.
        embedding: Vector embedding for the characteristic.
        
    Returns:
        Tuple of (success, error_message).
    """
    try:
        async with grpc.aio.insecure_channel(MILVUS_SERVICE_URL) as channel:
            stub = graph_milvus_pb2_grpc.GraphMilvusServiceStub(channel)
            request = graph_milvus_pb2.UpsertCharacteristicRequest(
                id=id,
                text=text,
                label_id=label_id,
                embedding=embedding
            )
            response = await stub.UpsertCharacteristic(request)
            return response.success, response.error_message
    except grpc.aio.AioRpcError as e:
        logging.error(f"gRPC error upserting characteristic: {e.details()}")
        raise e


async def upsert_characteristic_batch(
    characteristics: List[dict]
) -> Tuple[bool, str, int]:
    """
    Upsert multiple characteristics in a batch.
    
    Args:
        characteristics: List of dicts with 'id', 'text', 'label_id', and 'embedding' keys.
        
    Returns:
        Tuple of (success, error_message, inserted_count).
    """
    try:
        async with grpc.aio.insecure_channel(MILVUS_SERVICE_URL) as channel:
            stub = graph_milvus_pb2_grpc.GraphMilvusServiceStub(channel)
            
            char_items = [
                graph_milvus_pb2.CharacteristicItem(
                    id=c["id"],
                    text=c["text"],
                    label_id=c["label_id"],
                    embedding=c["embedding"]
                )
                for c in characteristics
            ]
            
            request = graph_milvus_pb2.UpsertCharacteristicBatchRequest(
                characteristics=char_items
            )
            response = await stub.UpsertCharacteristicBatch(request)
            return response.success, response.error_message, response.inserted_count
    except grpc.aio.AioRpcError as e:
        logging.error(f"gRPC error upserting characteristic batch: {e.details()}")
        raise e


async def search_similar_characteristics(
    embedding: List[float],
    top_k: int = 5,
    threshold: float = 0.8
) -> List[SearchResult]:
    """
    Search for similar characteristics.
    
    Args:
        embedding: Query vector embedding.
        top_k: Maximum number of results.
        threshold: Similarity threshold (0.0 - 1.0).
        
    Returns:
        List of SearchResult objects.
    """
    try:
        async with grpc.aio.insecure_channel(MILVUS_SERVICE_URL) as channel:
            stub = graph_milvus_pb2_grpc.GraphMilvusServiceStub(channel)
            request = graph_milvus_pb2.SearchCharacteristicsRequest(
                embedding=embedding,
                top_k=top_k,
                threshold=threshold
            )
            response = await stub.SearchSimilarCharacteristics(request)
            return [
                SearchResult(id=r.id, distance=r.distance, label=r.label)
                for r in response.results
            ]
    except grpc.aio.AioRpcError as e:
        logging.error(f"gRPC error searching characteristics: {e.details()}")
        raise e


# =============================================================================
# Collection Management
# =============================================================================

async def setup_collections(
    embedding_dimension: int = 1024
) -> Tuple[bool, str, List[str]]:
    """
    Setup required collections in Milvus.
    
    Args:
        embedding_dimension: Dimension of the embedding vectors.
        
    Returns:
        Tuple of (success, message, list of created collection names).
    """
    try:
        async with grpc.aio.insecure_channel(MILVUS_SERVICE_URL) as channel:
            stub = graph_milvus_pb2_grpc.GraphMilvusServiceStub(channel)
            request = graph_milvus_pb2.SetupCollectionsRequest(
                embedding_dimension=embedding_dimension
            )
            response = await stub.SetupCollections(request)
            return response.success, response.message, list(response.created_collections)
    except grpc.aio.AioRpcError as e:
        logging.error(f"gRPC error setting up collections: {e.details()}")
        raise e
