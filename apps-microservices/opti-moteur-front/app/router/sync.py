"""Routes de synchronisation incrementale Milvus -> Typesense."""
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Header
from pydantic import BaseModel, Field

from app.services.sync_service import sync_incremental


router = APIRouter(prefix="/sync", tags=["Sync"])


# Token jetable pour authentifier les appels du cron Ecritel.
# À changer en prod via env var SYNC_TOKEN.
import os
SYNC_TOKEN = os.getenv("SYNC_TOKEN", "hp_sync_2026_04_30_xZ7q")


class SyncRequest(BaseModel):
    since: Optional[str] = Field(
        None,
        description="ISO datetime: filtre date_maj >= since. Default = 24h ago.",
        example="2026-05-04T00:00:00",
    )
    ts_collection: Optional[str] = Field(
        None,
        description="Collection Typesense cible. Default = settings.TYPESENSE_COLLECTION.",
    )
    delete_orphans: bool = Field(
        True,
        description="Si True, supprime de Typesense les produits plus en Milvus.",
    )
    batch_size: int = Field(1000, ge=100, le=10000)


class SyncResponse(BaseModel):
    ts_collection: str
    since_iso: str
    milvus_recent_rows: int
    ts_upserted: int
    ts_upsert_errors: int
    ts_orphans_deleted: int
    duration_s: float
    ts_docs_before: int
    ts_docs_after: int


@router.post(
    "/incremental",
    response_model=SyncResponse,
    summary="Sync incremental Milvus -> Typesense (cron quotidien Ecritel)",
)
async def sync_incremental_endpoint(
    req: SyncRequest,
    x_sync_token: Optional[str] = Header(None, description="Token de securite (header)"),
):
    """
    Endpoint appele par le cron PHP Ecritel quotidiennement.

    Effet :
      1. Upsert les produits Milvus modifies depuis `since` (= NEW + UPDATED)
      2. Supprime les orphelins Typesense (= DELETED en Milvus)

    Securite : header `X-Sync-Token` requis.
    Duree typique : 5-30 minutes selon le volume de modifs.
    """
    if x_sync_token != SYNC_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid or missing X-Sync-Token header")

    try:
        result = sync_incremental(
            since_iso=req.since,
            ts_collection=req.ts_collection,
            delete_orphans=req.delete_orphans,
            batch_size=req.batch_size,
        )
        return SyncResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sync failed: {str(e)}")


@router.get(
    "/health",
    summary="Healthcheck du sync (verifie Milvus + Typesense)",
)
async def sync_health():
    """Verifie que Milvus et Typesense sont accessibles."""
    from app.core.milvus_connector import milvus
    from app.core.typesense_client import typesense_client
    from app.core.credentials import settings

    health = {"status": "ok", "milvus": "?", "typesense": "?"}

    try:
        col = milvus.get_collection(settings.MILVUS_COLLECTION)
        n = col.num_entities
        health["milvus"] = f"ok ({n} entities, collection={settings.MILVUS_COLLECTION})"
    except Exception as e:
        health["milvus"] = f"error: {e}"
        health["status"] = "degraded"

    try:
        info = typesense_client.collection_stats(settings.TYPESENSE_COLLECTION)
        health["typesense"] = f"ok ({info.get('num_documents', 0)} docs, collection={settings.TYPESENSE_COLLECTION})"
    except Exception as e:
        health["typesense"] = f"error: {e}"
        health["status"] = "degraded"

    return health
