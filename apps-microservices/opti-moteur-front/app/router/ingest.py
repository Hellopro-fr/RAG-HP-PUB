"""Routes d'ingestion Milvus -> Typesense."""
from fastapi import APIRouter, HTTPException, BackgroundTasks

from app.schemas.ingest import (
    IngestCategoryRequest, IngestCategoriesBatchRequest,
    CategoryIngestResult, IngestBatchResponse,
)
from app.services.ingestion_service import (
    ingest_by_category, ingest_categories_batch,
)

router = APIRouter(prefix="/ingest", tags=["Ingestion"])


@router.post(
    "/category",
    response_model=CategoryIngestResult,
    summary="Ingerer 1 categorie depuis Milvus",
)
async def ingest_single_category(req: IngestCategoryRequest):
    """Bloquant : attend la fin de l'ingestion de cette categorie avant de rendre."""
    try:
        return await ingest_by_category(
            categorie=req.categorie,
            ts_collection=req.ts_collection,
            extra_filter=req.extra_filter,
            batch_size=req.batch_size,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/categories/batch",
    response_model=IngestBatchResponse,
    summary="Ingerer plusieurs categories en serie",
)
async def ingest_batch(req: IngestCategoriesBatchRequest):
    """
    Ingestion sequentielle avec garde-fou disque. Bloquant.

    Pour les gros batches (>50 categories, >100k produits), preferer
    l'execution en background via /ingest/categories/batch/async
    ou via script CLI dedie (scripts/ingest_by_categories.py).
    """
    try:
        return await ingest_categories_batch(
            categories=req.categories,
            ts_collection=req.ts_collection,
            extra_filter=req.extra_filter,
            batch_size=req.batch_size,
            stop_if_disk_gb_below=req.stop_if_disk_gb_below,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
