import logging
import asyncio
import os
from typing import List, Dict, Any, Tuple, Optional

from pymilvus import (
    connections,
    Collection,
    FieldSchema,
    CollectionSchema,
    DataType,
    utility,
)

from app.config import settings


MILVUS_HOST = os.getenv("ZILLIZ_URI")
MILVUS_PORT = os.getenv("ZILLIZ_PORT", "19530")
MILVUS_USER = os.getenv("ZILLIZ_USER")
MILVUS_PASSWORD = os.getenv("ZILLIZ_PASSWORD")


class MilvusConnector:
    """
    Singleton connector for Milvus vector database operations.
    Manages entity, label, and characteristic collections for semantic deduplication.
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(MilvusConnector, cls).__new__(cls)
            cls._instance.collections: Dict[str, Collection] = {}
            cls._instance._connected = False
        return cls._instance

    def connect(self):
        """Connect to Milvus server."""
        if self._connected:
            return
        try:
            logging.info("Connecting to Milvus...")
            # connections.connect(
            #     "default",
            #     uri=settings.ZILLIZ_URI,
            #     token=settings.ZILLIZ_TOKEN if settings.ZILLIZ_TOKEN else None,
            # )
            connections.connect(
                "default",
                host=MILVUS_HOST,
                port=MILVUS_PORT,
                user=MILVUS_USER,
                password=MILVUS_PASSWORD,
            )
            self._connected = True
            logging.info("Successfully connected to Milvus.")
        except Exception as e:
            logging.critical(f"Failed to connect to Milvus: {e}", exc_info=True)
            raise

    def _setup_collection(
        self, collection_name: str, schema: CollectionSchema, vector_field: str
    ):
        """Setup a collection with HNSW index."""
        if utility.has_collection(collection_name):
            logging.info(f"Milvus collection '{collection_name}' already exists.")
            self.collections[collection_name] = Collection(collection_name)
        else:
            logging.info(
                f"Milvus collection '{collection_name}' not found, creating..."
            )
            self.collections[collection_name] = Collection(collection_name, schema)
            index_params = {
                "metric_type": "COSINE",
                "index_type": "HNSW",
                "params": {"M": 32, "efConstruction": 300},
            }
            self.collections[collection_name].create_index(
                field_name=vector_field, index_params=index_params
            )
            logging.info(
                f"Successfully created collection '{collection_name}' with HNSW/COSINE index."
            )

        self.collections[collection_name].load()
        logging.info(f"Collection '{collection_name}' loaded into memory.")

    def setup_collections(self, embedding_dim: int = None) -> List[str]:
        """Setup all required collections."""
        if embedding_dim is None:
            embedding_dim = settings.EMBEDDING_DIMENSION

        created = []
        try:
            # Entity collection (for semantic vigil)
            entity_fields = [
                FieldSchema(
                    name="id", dtype=DataType.VARCHAR, is_primary=True, max_length=512
                ),
                FieldSchema(name="entity_type", dtype=DataType.VARCHAR, max_length=256),
                FieldSchema(
                    name="embedding", dtype=DataType.FLOAT_VECTOR, dim=embedding_dim
                ),
            ]
            entity_schema = CollectionSchema(
                entity_fields, "Canonical entities for semantic deduplication"
            )
            self._setup_collection(
                settings.MILVUS_ENTITY_COLLECTION, entity_schema, "embedding"
            )
            created.append(settings.MILVUS_ENTITY_COLLECTION)

            # Label collection (for characteristic label deduplication)
            label_fields = [
                FieldSchema(
                    name="label",
                    dtype=DataType.VARCHAR,
                    is_primary=True,
                    max_length=512,
                ),
                FieldSchema(
                    name="embedding", dtype=DataType.FLOAT_VECTOR, dim=embedding_dim
                ),
            ]
            label_schema = CollectionSchema(
                label_fields, "Canonical labels for characteristics"
            )
            self._setup_collection(
                settings.MILVUS_LABEL_COLLECTION, label_schema, "embedding"
            )
            created.append(settings.MILVUS_LABEL_COLLECTION)

            # Characteristic collection (for characteristic value deduplication)
            characteristic_fields = [
                FieldSchema(
                    name="id", dtype=DataType.VARCHAR, is_primary=True, max_length=512
                ),
                FieldSchema(name="text", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="label_id", dtype=DataType.VARCHAR, max_length=512),
                FieldSchema(
                    name="embedding", dtype=DataType.FLOAT_VECTOR, dim=embedding_dim
                ),
            ]
            characteristic_schema = CollectionSchema(
                characteristic_fields, "Embeddings of individual characteristics"
            )
            self._setup_collection(
                settings.MILVUS_CHARACTERISTIC_COLLECTION,
                characteristic_schema,
                "embedding",
            )
            created.append(settings.MILVUS_CHARACTERISTIC_COLLECTION)

            return created
        except Exception as e:
            logging.critical(f"Failed to setup Milvus collections: {e}", exc_info=True)
            raise

    def _get_collection(self, name: str) -> Optional[Collection]:
        """Get a collection by name."""
        collection = self.collections.get(name)
        if not collection:
            logging.error(f"Milvus collection '{name}' not initialized.")
        return collection

    # --- Entity Operations ---
    async def check_entities_exist(self, ids: List[str]) -> List[str]:
        """Check which entity IDs already exist in the collection."""
        collection = self._get_collection(settings.MILVUS_ENTITY_COLLECTION)
        if not collection or not ids:
            return []
        ids_formatted = ", ".join([f'"{id_}"' for id_ in ids])
        expr = f"id in [{ids_formatted}]"
        try:
            results = await asyncio.to_thread(
                collection.query, expr=expr, output_fields=["id"]
            )
            return [res["id"] for res in results]
        except Exception as e:
            logging.error(f"Error during Milvus entity ID check: {e}", exc_info=True)
            return []

    async def search_similar_entities(
        self,
        vector: List[float],
        entity_type: str,
        top_k: int = 1,
        threshold: float = 0.9,
    ) -> List[Tuple[str, float]]:
        """Search for similar entities by embedding vector."""
        collection = self._get_collection(settings.MILVUS_ENTITY_COLLECTION)
        if not collection or not vector:
            return []

        search_params = {
            "metric_type": "COSINE",
            "params": {"ef": 128},
        }
        filter_expr = f"entity_type == '{entity_type}'"

        try:
            results = await asyncio.to_thread(
                collection.search,
                data=[vector],
                anns_field="embedding",
                param=search_params,
                limit=top_k,
                expr=filter_expr,
                output_fields=["id"],
            )
            return [
                (hit.entity.get("id"), hit.distance)
                for hit in results[0]
                if hit.distance >= threshold
            ]
        except Exception as e:
            logging.error(f"Error during Milvus entity search: {e}", exc_info=True)
            return []

    async def insert_entity(
        self, id_: str, entity_type: str, embedding: List[float]
    ) -> bool:
        """Insert a single entity."""
        return await self.insert_entities_batch(
            [{"id": id_, "type": entity_type, "vector": embedding}]
        )

    async def insert_entities_batch(self, batch: List[Dict]) -> bool:
        """Insert a batch of entities."""
        collection = self._get_collection(settings.MILVUS_ENTITY_COLLECTION)
        if not collection or not batch:
            return False
        try:
            data = [
                [item["id"] for item in batch],
                [item["type"] for item in batch],
                [item["vector"] for item in batch],
            ]
            await asyncio.to_thread(collection.insert, data)
            await asyncio.to_thread(collection.flush)
            logging.info(f"Inserted {len(batch)} entities into Milvus.")
            return True
        except Exception as e:
            logging.error(f"Error inserting entity batch: {e}", exc_info=True)
            return False

    # --- Label Operations ---
    async def check_labels_exist(self, labels: List[str]) -> List[str]:
        """Check which labels already exist in the collection."""
        collection = self._get_collection(settings.MILVUS_LABEL_COLLECTION)
        if not collection or not labels:
            return []
        labels_formatted = ", ".join([f'"{label}"' for label in labels])
        expr = f"label in [{labels_formatted}]"
        try:
            results = await asyncio.to_thread(
                collection.query, expr=expr, output_fields=["label"]
            )
            return [res["label"] for res in results]
        except Exception as e:
            logging.error(f"Error during Milvus label check: {e}", exc_info=True)
            return []

    async def search_similar_labels(
        self,
        vector: List[float],
        top_k: int = 1,
        threshold: float = 0.9,
    ) -> List[Tuple[str, float]]:
        """Search for similar labels by embedding vector."""
        collection = self._get_collection(settings.MILVUS_LABEL_COLLECTION)
        if not collection or not vector:
            return []
        search_params = {
            "metric_type": "COSINE",
            "params": {"ef": 128},
        }
        try:
            results = await asyncio.to_thread(
                collection.search,
                data=[vector],
                anns_field="embedding",
                param=search_params,
                limit=top_k,
                output_fields=["label"],
            )
            return [
                (hit.entity.get("label"), hit.distance)
                for hit in results[0]
                if hit.distance >= threshold
            ]
        except Exception as e:
            logging.error(f"Error during Milvus label search: {e}", exc_info=True)
            return []

    async def insert_label(self, label: str, embedding: List[float]) -> bool:
        """Insert a single label."""
        return await self.insert_labels_batch([{"label": label, "vector": embedding}])

    async def insert_labels_batch(self, batch: List[Dict]) -> bool:
        """Insert a batch of labels."""
        collection = self._get_collection(settings.MILVUS_LABEL_COLLECTION)
        if not collection or not batch:
            return False
        try:
            data = [
                [item["label"] for item in batch],
                [item["vector"] for item in batch],
            ]
            await asyncio.to_thread(collection.insert, data)
            await asyncio.to_thread(collection.flush)
            logging.info(f"Inserted {len(batch)} labels into Milvus.")
            return True
        except Exception as e:
            logging.error(f"Error inserting label batch: {e}", exc_info=True)
            return False

    # --- Characteristic Operations ---
    async def search_similar_characteristics(
        self,
        vector: List[float],
        top_k: int = 5,
        threshold: float = 0.8,
    ) -> List[Dict[str, Any]]:
        """Search for similar characteristics by embedding vector."""
        collection = self._get_collection(settings.MILVUS_CHARACTERISTIC_COLLECTION)
        if not collection or not vector:
            return []

        search_params = {
            "metric_type": "COSINE",
            "params": {"ef": 128},
        }
        try:
            results = await asyncio.to_thread(
                collection.search,
                data=[vector],
                anns_field="embedding",
                param=search_params,
                limit=top_k,
                output_fields=["id"],
            )
            return [
                {"id": hit.entity.get("id"), "distance": hit.distance}
                for hit in results[0]
                if hit.distance >= threshold
            ]
        except Exception as e:
            logging.error(
                f"Error during Milvus characteristic search: {e}", exc_info=True
            )
            return []

    async def insert_characteristic(
        self, id_: str, text: str, label_id: str, embedding: List[float]
    ) -> bool:
        """Insert a single characteristic."""
        return await self.insert_characteristics_batch(
            [{"id": id_, "text": text, "label_id": label_id, "embedding": embedding}]
        )

    async def insert_characteristics_batch(self, batch: List[Dict]) -> bool:
        """Insert a batch of characteristics."""
        collection = self._get_collection(settings.MILVUS_CHARACTERISTIC_COLLECTION)
        if not collection or not batch:
            return False
        try:
            data = [
                [item["id"] for item in batch],
                [item["text"] for item in batch],
                [item["label_id"] for item in batch],
                [item["embedding"] for item in batch],
            ]
            await asyncio.to_thread(collection.insert, data)
            await asyncio.to_thread(collection.flush)
            logging.info(f"Inserted {len(batch)} characteristics into Milvus.")
            return True
        except Exception as e:
            logging.error(f"Error inserting characteristic batch: {e}", exc_info=True)
            return False

    def disconnect(self):
        """Disconnect from Milvus."""
        if self._connected:
            connections.disconnect("default")
            self._connected = False
            logging.info("Disconnected from Milvus.")


# Singleton instance
milvus_connector = MilvusConnector()
