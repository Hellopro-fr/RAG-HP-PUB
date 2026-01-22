import grpc
import logging
from concurrent import futures

from grpc_stubs import graph_milvus_pb2
from grpc_stubs import graph_milvus_pb2_grpc

from application.milvus_use_case import MilvusUseCase
from app.config import settings


class GraphMilvusServiceImpl(graph_milvus_pb2_grpc.GraphMilvusServiceServicer):
    """gRPC service implementation for Milvus canonical operations."""

    def __init__(self, use_case: MilvusUseCase):
        self.use_case = use_case

    # --- Entity Operations ---
    async def UpsertCanonicalEntity(self, request, context):
        """Upsert a single canonical entity."""
        logging.info(
            f"UpsertCanonicalEntity: id={request.id}, type={request.entity_type}"
        )
        try:
            success = await self.use_case.upsert_entity(
                id_=request.id,
                entity_type=request.entity_type,
                embedding=list(request.embedding),
            )
            return graph_milvus_pb2.UpsertResponse(success=success, error_message="")
        except Exception as e:
            logging.error(f"UpsertCanonicalEntity error: {e}", exc_info=True)
            return graph_milvus_pb2.UpsertResponse(success=False, error_message=str(e))

    async def UpsertEntityBatch(self, request, context):
        """Upsert a batch of entities."""
        logging.info(f"UpsertEntityBatch: {len(request.entities)} entities")
        try:
            entities = [
                {
                    "id": e.id,
                    "entity_type": e.entity_type,
                    "embedding": list(e.embedding),
                }
                for e in request.entities
            ]
            count = await self.use_case.upsert_entity_batch(entities)
            return graph_milvus_pb2.UpsertBatchResponse(
                success=count > 0, error_message="", inserted_count=count
            )
        except Exception as e:
            logging.error(f"UpsertEntityBatch error: {e}", exc_info=True)
            return graph_milvus_pb2.UpsertBatchResponse(
                success=False, error_message=str(e), inserted_count=0
            )

    async def SearchSimilarEntities(self, request, context):
        """Search for similar entities."""
        logging.info(
            f"SearchSimilarEntities: type={request.entity_type}, top_k={request.top_k}"
        )
        try:
            results = await self.use_case.search_similar_entities(
                embedding=list(request.embedding),
                entity_type=request.entity_type,
                top_k=request.top_k,
                threshold=request.threshold,
            )
            return graph_milvus_pb2.SearchResponse(
                results=[
                    graph_milvus_pb2.SearchResult(id=id_, distance=dist)
                    for id_, dist in results
                ]
            )
        except Exception as e:
            logging.error(f"SearchSimilarEntities error: {e}", exc_info=True)
            return graph_milvus_pb2.SearchResponse(results=[])

    async def CheckEntitiesExist(self, request, context):
        """Check which entities exist."""
        logging.info(f"CheckEntitiesExist: {len(request.ids)} ids")
        try:
            existing = await self.use_case.check_entities_exist(list(request.ids))
            return graph_milvus_pb2.CheckExistResponse(existing_ids=existing)
        except Exception as e:
            logging.error(f"CheckEntitiesExist error: {e}", exc_info=True)
            return graph_milvus_pb2.CheckExistResponse(existing_ids=[])

    # --- Label Operations ---
    async def UpsertCanonicalLabel(self, request, context):
        """Upsert a single canonical label."""
        logging.info(f"UpsertCanonicalLabel: label={request.label}")
        try:
            success = await self.use_case.upsert_label(
                label=request.label, embedding=list(request.embedding)
            )
            return graph_milvus_pb2.UpsertResponse(success=success, error_message="")
        except Exception as e:
            logging.error(f"UpsertCanonicalLabel error: {e}", exc_info=True)
            return graph_milvus_pb2.UpsertResponse(success=False, error_message=str(e))

    async def UpsertLabelBatch(self, request, context):
        """Upsert a batch of labels."""
        logging.info(f"UpsertLabelBatch: {len(request.labels)} labels")
        try:
            labels = [
                {"label": l.label, "embedding": list(l.embedding)}
                for l in request.labels
            ]
            count = await self.use_case.upsert_label_batch(labels)
            return graph_milvus_pb2.UpsertBatchResponse(
                success=count > 0, error_message="", inserted_count=count
            )
        except Exception as e:
            logging.error(f"UpsertLabelBatch error: {e}", exc_info=True)
            return graph_milvus_pb2.UpsertBatchResponse(
                success=False, error_message=str(e), inserted_count=0
            )

    async def SearchSimilarLabels(self, request, context):
        """Search for similar labels."""
        logging.info(f"SearchSimilarLabels: top_k={request.top_k}")
        try:
            results = await self.use_case.search_similar_labels(
                embedding=list(request.embedding),
                top_k=request.top_k,
                threshold=request.threshold,
            )
            return graph_milvus_pb2.SearchResponse(
                results=[
                    graph_milvus_pb2.SearchResult(label=label, distance=dist)
                    for label, dist in results
                ]
            )
        except Exception as e:
            logging.error(f"SearchSimilarLabels error: {e}", exc_info=True)
            return graph_milvus_pb2.SearchResponse(results=[])

    async def CheckLabelsExist(self, request, context):
        """Check which labels exist."""
        logging.info(f"CheckLabelsExist: {len(request.labels)} labels")
        try:
            existing = await self.use_case.check_labels_exist(list(request.labels))
            return graph_milvus_pb2.CheckLabelsExistResponse(existing_labels=existing)
        except Exception as e:
            logging.error(f"CheckLabelsExist error: {e}", exc_info=True)
            return graph_milvus_pb2.CheckLabelsExistResponse(existing_labels=[])

    # --- Characteristic Operations ---
    async def UpsertCharacteristic(self, request, context):
        """Upsert a single characteristic."""
        logging.info(f"UpsertCharacteristic: id={request.id}")
        try:
            success = await self.use_case.upsert_characteristic(
                id_=request.id,
                text=request.text,
                label_id=request.label_id,
                embedding=list(request.embedding),
            )
            return graph_milvus_pb2.UpsertResponse(success=success, error_message="")
        except Exception as e:
            logging.error(f"UpsertCharacteristic error: {e}", exc_info=True)
            return graph_milvus_pb2.UpsertResponse(success=False, error_message=str(e))

    async def UpsertCharacteristicBatch(self, request, context):
        """Upsert a batch of characteristics."""
        logging.info(f"UpsertCharacteristicBatch: {len(request.characteristics)} items")
        try:
            characteristics = [
                {
                    "id": c.id,
                    "text": c.text,
                    "label_id": c.label_id,
                    "embedding": list(c.embedding),
                }
                for c in request.characteristics
            ]
            count = await self.use_case.upsert_characteristic_batch(characteristics)
            return graph_milvus_pb2.UpsertBatchResponse(
                success=count > 0, error_message="", inserted_count=count
            )
        except Exception as e:
            logging.error(f"UpsertCharacteristicBatch error: {e}", exc_info=True)
            return graph_milvus_pb2.UpsertBatchResponse(
                success=False, error_message=str(e), inserted_count=0
            )

    async def SearchSimilarCharacteristics(self, request, context):
        """Search for similar characteristics."""
        logging.info(f"SearchSimilarCharacteristics: top_k={request.top_k}")
        try:
            results = await self.use_case.search_similar_characteristics(
                embedding=list(request.embedding),
                top_k=request.top_k,
                threshold=request.threshold,
            )
            return graph_milvus_pb2.SearchResponse(
                results=[
                    graph_milvus_pb2.SearchResult(id=r["id"], distance=r["distance"])
                    for r in results
                ]
            )
        except Exception as e:
            logging.error(f"SearchSimilarCharacteristics error: {e}", exc_info=True)
            return graph_milvus_pb2.SearchResponse(results=[])

    # --- Collection Management ---
    async def SetupCollections(self, request, context):
        """Setup all collections."""
        logging.info(f"SetupCollections: dim={request.embedding_dimension}")
        try:
            created = self.use_case.setup_collections(
                request.embedding_dimension if request.embedding_dimension > 0 else None
            )
            return graph_milvus_pb2.SetupCollectionsResponse(
                success=True,
                message=f"Created {len(created)} collections",
                created_collections=created,
            )
        except Exception as e:
            logging.error(f"SetupCollections error: {e}", exc_info=True)
            return graph_milvus_pb2.SetupCollectionsResponse(
                success=False, message=str(e), created_collections=[]
            )


async def serve(use_case: MilvusUseCase):
    """Start the gRPC server."""
    server = grpc.aio.server(
        futures.ThreadPoolExecutor(max_workers=settings.GRPC_MAX_WORKERS)
    )
    graph_milvus_pb2_grpc.add_GraphMilvusServiceServicer_to_server(
        GraphMilvusServiceImpl(use_case), server
    )
    server.add_insecure_port(f"[::]:{settings.GRPC_PORT}")
    logging.info(f"gRPC Graph Milvus Service started on port {settings.GRPC_PORT}...")
    await server.start()
    await server.wait_for_termination()
