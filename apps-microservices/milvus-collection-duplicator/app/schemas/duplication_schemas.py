from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class DuplicationRequest(BaseModel):
    source_collection: str = Field(
        ...,
        description="Name of the source Milvus collection to duplicate",
        examples=["produits_3"],
    )
    target_collection: str = Field(
        ...,
        description="Name of the new target collection to create",
        examples=["produits_4"],
    )
    text_field: str = Field(
        default="text",
        description="Name of the VARCHAR field used for BM25 sparse embedding generation",
    )
    batch_size: int = Field(
        default=500,
        ge=100,
        le=5000,
        description="Number of records to copy per batch",
    )
    analyzer_language: str = Field(
        default="english",
        description="Language for the BM25 text analyzer (e.g., 'english', 'french')",
    )
    limit: Optional[int] = Field(
        default=None,
        ge=1,
        description="Optional max number of rows to migrate (for testing). If None, all rows are copied.",
    )
    parallel_workers: int = Field(
        default=1,
        ge=1,
        le=10,
        description="Number of parallel insert workers (1=sequential, higher=faster but more resource-intensive)",
    )
    float_vector_index_type: Optional[str] = Field(
        default=None,
        description=(
            "Override the index type for all FLOAT_VECTOR fields in the target collection. "
            "Accepted values: FLAT, IVF_FLAT, IVF_SQ8, IVF_PQ, HNSW, DISKANN, AUTOINDEX. "
            "If None, the source index is copied as-is."
        ),
        examples=["HNSW", "IVF_FLAT", "DISKANN"],
    )
    float_vector_index_params: Optional[dict] = Field(
        default=None,
        description=(
            "Extra index build parameters for FLOAT_VECTOR fields (used only when "
            'float_vector_index_type is set). Example: {"M": 16, "efConstruction": 256} for HNSW.'
        ),
    )


class DuplicationResponse(BaseModel):
    job_id: str
    message: str
    status: JobStatus


class JobStatusResponse(BaseModel):
    job_id: str
    status: JobStatus
    total_source_entities: Optional[int] = None
    records_copied: int = 0
    message: str = ""
    error: Optional[str] = None
    error_file: Optional[str] = None


class RetryRequest(BaseModel):
    source_collection: str = Field(
        ...,
        description="Name of the source Milvus collection to read failed rows from",
    )
    target_collection: str = Field(
        ...,
        description="Name of the target collection to re-insert into",
    )
    error_file: str = Field(
        ...,
        description="Filename of the error TXT file (e.g., 'errors_<job_id>.txt')",
    )
    text_field: str = Field(
        default="text",
        description="VARCHAR field used for BM25 generation (must match the target schema)",
    )
    batch_size: int = Field(
        default=100,
        ge=1,
        le=5000,
        description="Number of records to re-insert per batch",
    )


class RetryResponse(BaseModel):
    total_retried: int
    total_succeeded: int
    total_still_failed: int
    new_error_file: Optional[str] = None
    message: str


class RenameCollectionRequest(BaseModel):
    old_collection_name: str = Field(
        ...,
        description="Current name of the Milvus collection to rename",
        examples=["produits_3"],
    )
    new_collection_name: str = Field(
        ...,
        description="New name for the collection",
        examples=["produits_4"],
    )


class RenameCollectionResponse(BaseModel):
    old_collection_name: str
    new_collection_name: str
    message: str
