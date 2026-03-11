from fastapi import FastAPI
from app.router.duplication_router import duplication_router

import logging
import asyncio
from contextlib import asynccontextmanager

from app.core.milvus_connection import connect_milvus


logger = logging.getLogger(__name__)

description = """
## Milvus Collection Duplicator

Duplicate a Milvus collection with all its data and add a `sparse_embedding` field
powered by Milvus 2.6 built-in **BM25 Function**.

### Features
- **Schema cloning** via `copy.deepcopy` — preserves all field params automatically
- **Built-in BM25** — Milvus auto-generates sparse vectors from the text field on insert
- **1M+ rows** — uses `query_iterator` for efficient streaming pagination
- **Background processing** — long-running jobs execute in background threads
"""

PROJECT_NAME__ = "Milvus Collection Duplicator"
PROJECT_VERSION__ = "1.0.0"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handles application startup and shutdown events."""
    logger.info("--- Application Startup ---")

    # Connect to Milvus in a separate thread to avoid blocking
    await asyncio.to_thread(connect_milvus)

    logger.info("--- Startup Complete. Application is ready. ---")

    yield

    # --- Shutdown Logic ---
    logger.info("--- Application Shutdown ---")


app = FastAPI(
    title=PROJECT_NAME__,
    version=PROJECT_VERSION__,
    description=description,
    lifespan=lifespan,
)


@app.get("/", tags=["Monitoring"])
def read_root():
    return {"message": f"Bienvenue sur l'API {PROJECT_NAME__} v{PROJECT_VERSION__}"}


@app.get("/health", tags=["Monitoring"])
def health_check():
    return {"status": "ok"}


app.include_router(duplication_router)
