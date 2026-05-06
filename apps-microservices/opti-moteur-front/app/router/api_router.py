"""Aggregation des routeurs FastAPI."""
from fastapi import APIRouter

from .search import router as search_router
from .search_text import router as search_text_router
from .ingest import router as ingest_router
from .admin import router as admin_router
from .sync import router as sync_router

api_router = APIRouter()
api_router.include_router(search_router)
api_router.include_router(search_text_router)
api_router.include_router(ingest_router)
api_router.include_router(admin_router)
api_router.include_router(sync_router)
