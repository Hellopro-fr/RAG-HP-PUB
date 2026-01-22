from typing import List, Dict, Any, Tuple

from infrastructure.milvus_connector import milvus_connector


class MilvusUseCase:
    """
    Application layer use case for Milvus canonical operations.
    Orchestrates connector calls for entities, labels, and characteristics.
    """

    def __init__(self):
        self.connector = milvus_connector

    # --- Entity Operations ---
    async def upsert_entity(
        self, id_: str, entity_type: str, embedding: List[float]
    ) -> bool:
        """Upsert a single entity."""
        return await self.connector.insert_entity(id_, entity_type, embedding)

    async def upsert_entity_batch(self, entities: List[Dict[str, Any]]) -> int:
        """Upsert a batch of entities. Returns count of inserted."""
        batch = [
            {"id": e["id"], "type": e["entity_type"], "vector": e["embedding"]}
            for e in entities
        ]
        success = await self.connector.insert_entities_batch(batch)
        return len(batch) if success else 0

    async def search_similar_entities(
        self, embedding: List[float], entity_type: str, top_k: int, threshold: float
    ) -> List[Tuple[str, float]]:
        """Search for similar entities."""
        return await self.connector.search_similar_entities(
            embedding, entity_type, top_k, threshold
        )

    async def check_entities_exist(self, ids: List[str]) -> List[str]:
        """Check which entity IDs exist."""
        return await self.connector.check_entities_exist(ids)

    # --- Label Operations ---
    async def upsert_label(self, label: str, embedding: List[float]) -> bool:
        """Upsert a single label."""
        return await self.connector.insert_label(label, embedding)

    async def upsert_label_batch(self, labels: List[Dict[str, Any]]) -> int:
        """Upsert a batch of labels. Returns count of inserted."""
        batch = [{"label": l["label"], "vector": l["embedding"]} for l in labels]
        success = await self.connector.insert_labels_batch(batch)
        return len(batch) if success else 0

    async def search_similar_labels(
        self, embedding: List[float], top_k: int, threshold: float
    ) -> List[Tuple[str, float]]:
        """Search for similar labels."""
        return await self.connector.search_similar_labels(embedding, top_k, threshold)

    async def check_labels_exist(self, labels: List[str]) -> List[str]:
        """Check which labels exist."""
        return await self.connector.check_labels_exist(labels)

    # --- Characteristic Operations ---
    async def upsert_characteristic(
        self, id_: str, text: str, label_id: str, embedding: List[float]
    ) -> bool:
        """Upsert a single characteristic."""
        return await self.connector.insert_characteristic(
            id_, text, label_id, embedding
        )

    async def upsert_characteristic_batch(
        self, characteristics: List[Dict[str, Any]]
    ) -> int:
        """Upsert a batch of characteristics. Returns count of inserted."""
        batch = [
            {
                "id": c["id"],
                "text": c["text"],
                "label_id": c["label_id"],
                "embedding": c["embedding"],
            }
            for c in characteristics
        ]
        success = await self.connector.insert_characteristics_batch(batch)
        return len(batch) if success else 0

    async def search_similar_characteristics(
        self, embedding: List[float], top_k: int, threshold: float
    ) -> List[Dict[str, Any]]:
        """Search for similar characteristics."""
        return await self.connector.search_similar_characteristics(
            embedding, top_k, threshold
        )

    # --- Collection Management ---
    def setup_collections(self, embedding_dimension: int = None) -> List[str]:
        """Setup all collections."""
        return self.connector.setup_collections(embedding_dimension)
