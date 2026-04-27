"""Schemas pydantic pour l'API d'ingestion."""
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class IngestCategoryRequest(BaseModel):
    categorie: str = Field(..., description="Nom de la categorie a ingerer")
    ts_collection: Optional[str] = Field(None, description="Collection Typesense cible")
    extra_filter: Optional[str] = Field(
        None,
        description="Expression Milvus additionnelle (ex: etat in [\"Client\",\"Prospect\"])",
    )
    batch_size: int = Field(1000, ge=100, le=10000, description="Taille des batches Typesense")


class IngestCategoriesBatchRequest(BaseModel):
    categories: List[str] = Field(..., description="Liste des categories a ingerer en serie")
    ts_collection: Optional[str] = None
    extra_filter: Optional[str] = None
    batch_size: int = 1000
    stop_if_disk_gb_below: float = Field(3.0, description="Arret preventif si disque < threshold")


class CategoryIngestResult(BaseModel):
    categorie: str
    chunks_milvus: int = 0
    chunks_ok: int = 0
    chunks_err: int = 0
    typesense_docs: int = 0
    disk_free_gb: float = 0
    latency_ms: Dict[str, int] = Field(default_factory=dict)
    error: Optional[str] = None


class IngestBatchResponse(BaseModel):
    categories_processed: int
    categories_total: int
    total_chunks_milvus: int
    total_chunks_ok: int
    stopped_reason: Optional[str] = None
    elapsed_s: float
    per_category: List[CategoryIngestResult]
