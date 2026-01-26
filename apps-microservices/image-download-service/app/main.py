import logging
import threading
from typing import List, Optional
from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from contextlib import asynccontextmanager
from app.messaging.consumer import Consumer
from app.messaging.publisher import Publisher
from app.core.archiver import Archiver

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("image-download-service")

# Request/Response Models
class SyncRequest(BaseModel):
    product_ids: Optional[List[str]] = None  # None = mark all as synced

class SyncStatusResponse(BaseModel):
    domain: str
    exists: bool
    total_products: int
    synced_products: int
    unsynced_products: int
    last_updated: Optional[str] = None
    last_sync: Optional[str] = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("🚀 Image-Download-Service: Starting up...")
    
    # Initialize Publisher
    app.state.publisher = Publisher()
    
    # Initialize Consumer and start in background thread
    app.state.consumer = Consumer(app.state.publisher)
    consumer_thread = threading.Thread(target=app.state.consumer.start_consuming, daemon=True)
    consumer_thread.start()
    
    yield
    
    # Shutdown
    logger.info("🛑 Image-Download-Service: Shutting down...")
    if app.state.consumer.connection:
        app.state.consumer.connection.close()

app = FastAPI(
    title="Image Download Service",
    description="Service for downloading, processing, and archiving product images with incremental sync support",
    version="2.0.0",
    lifespan=lifespan,
    openapi_tags=[
        {
            "name": "Health",
            "description": "Service health checks",
        },
        {
            "name": "Archives",
            "description": "Create and download image archives (full or delta)",
        },
        {
            "name": "Sync",
            "description": "Synchronization status and management",
        },
        {
            "name": "Domains",
            "description": "Domain management and listing",
        }
    ]
)

archiver = Archiver()

# =============================================================================
# HEALTH
# =============================================================================

@app.get("/health", tags=["Health"])
def health_check():
    """Health check endpoint for the service."""
    return {"status": "ok", "service": "image-download-service", "version": "2.0.0"}

# =============================================================================
# DOMAINS
# =============================================================================

@app.get("/domains", tags=["Domains"])
async def list_domains():
    """
    List all domains that have images stored.
    
    **Returns:**
    - List of domain names with images
    """
    domains = await archiver.list_domains()
    return {"domains": domains, "count": len(domains)}

@app.get("/domains/recent", tags=["Domains"])
async def get_recent_domains(hours: int = 6):
    """
    Get domains with images processed in the last X hours.
    Use this endpoint for the cron to know which domains to archive.
    
    **Parameters:**
    - `hours`: Number of hours to look back (default: 6)
    
    **Returns:**
    - List of domains with activity, sorted by most recent
    
    **Example response:**
    ```json
    {
      "domains": [
        {
          "domain": "tech-shop.com",
          "last_updated": "2026-01-26T08:30:00",
          "total_products": 150,
          "unsynced_products": 25,
          "hours_ago": 0.5
        }
      ],
      "count": 1,
      "hours_checked": 6
    }
    ```
    """
    domains = await archiver.get_recent_domains(hours)
    return {
        "domains": domains,
        "count": len(domains),
        "hours_checked": hours
    }

@app.get("/domains/{domain}/status", tags=["Domains"])
async def get_domain_sync_status(domain: str):
    """
    Get synchronization status for a specific domain.
    
    **Parameters:**
    - `domain`: The domain name
    
    **Returns:**
    - Total products, synced count, unsynced count, last sync time
    """
    status = await archiver.get_sync_status(domain)
    return status

# =============================================================================
# ARCHIVES
# =============================================================================

@app.post("/archive/delta/{domain}", tags=["Archives"])
async def create_delta_archive(domain: str):
    """
    Creates a DELTA archive containing only NEW (unsynced) products.
    Use this for daily cron synchronization.
    
    **Parameters:**
    - `domain`: The domain name
    
    **Returns:**
    - The delta archive file (.tar.gz) containing only unsynced images
    - Or a message if all products are already synced
    """
    try:
        result = await archiver.create_delta_archive(domain)
        
        if result["archive_path"] is None:
            return JSONResponse(
                status_code=200,
                content={
                    "status": "no_changes",
                    "message": result["message"],
                    "product_count": 0
                }
            )
        
        # Return the archive as a downloadable file
        return FileResponse(
            result["archive_path"],
            media_type="application/gzip",
            filename=f"{domain}_delta.tar.gz",
            headers={
                "Content-Disposition": f'attachment; filename="{domain}_delta.tar.gz"',
                "X-Product-Count": str(result["product_count"]),
                "X-Product-Ids": ",".join(result["product_ids"][:50])  # Limit header size
            }
        )
    except ValueError as e:
        return JSONResponse(status_code=404, content={"status": "error", "message": str(e)})
    except Exception as e:
        logger.error(f"Delta archive error: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": "Internal server error"})

@app.post("/archive/full/{domain}", tags=["Archives"])
async def create_full_archive(domain: str):
    """
    Creates a FULL archive containing ALL products (synced and unsynced).
    Use this for initial sync or disaster recovery.
    
    **Parameters:**
    - `domain`: The domain name
    
    **Returns:**
    - The complete archive file (.tar.gz) with all images
    """
    try:
        path = await archiver.create_full_archive(domain)
        
        return FileResponse(
            path,
            media_type="application/gzip",
            filename=f"{domain}_full.tar.gz",
            headers={"Content-Disposition": f'attachment; filename="{domain}_full.tar.gz"'}
        )
    except ValueError as e:
        return JSONResponse(status_code=404, content={"status": "error", "message": str(e)})
    except Exception as e:
        logger.error(f"Full archive error: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": "Internal server error"})

@app.get("/archives", tags=["Archives"])
async def list_archives():
    """
    List all available archives.
    
    **Returns:**
    - List of archive files with metadata (size, creation date)
    """
    archives = await archiver.list_archives()
    return {"archives": archives, "count": len(archives)}

@app.post("/archives/cleanup", tags=["Archives"])
async def cleanup_archives(domain: str = None, keep_latest: int = 3):
    """
    Delete old archives, keeping only the N most recent per domain.
    Call this after successful download to free up disk space.
    
    **Parameters:**
    - `domain` (optional): Specific domain to cleanup. If not provided, cleans all domains.
    - `keep_latest`: Number of recent archives to keep per domain (default: 3)
    
    **Returns:**
    - Number of archives deleted
    """
    try:
        deleted = await archiver.cleanup_old_archives(domain, keep_latest)
        return {
            "status": "success",
            "deleted_count": deleted,
            "domain": domain or "all",
            "kept_latest": keep_latest
        }
    except Exception as e:
        logger.error(f"Cleanup error: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

# =============================================================================
# SYNC MANAGEMENT
# =============================================================================

@app.post("/sync/{domain}", tags=["Sync"])
async def mark_synced(domain: str, request: SyncRequest = None):
    """
    Mark products as synced after successful download by the Back-Office.
    Call this AFTER successfully downloading and extracting the delta archive.
    
    **Parameters:**
    - `domain`: The domain name
    - `product_ids` (body, optional): List of product IDs to mark as synced. 
      If not provided, marks ALL products as synced.
    
    **Example body:**
    ```json
    {"product_ids": ["60001", "60002", "60003"]}
    ```
    Or to mark all:
    ```json
    {}
    ```
    """
    try:
        product_ids = request.product_ids if request else None
        count = await archiver.mark_products_synced(domain, product_ids)
        return {
            "status": "success",
            "domain": domain,
            "synced_count": count,
            "synced_all": product_ids is None
        }
    except ValueError as e:
        return JSONResponse(status_code=404, content={"status": "error", "message": str(e)})
    except Exception as e:
        logger.error(f"Sync error: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": "Internal server error"})

@app.get("/sync/{domain}/pending", tags=["Sync"])
async def get_pending_products(domain: str):
    """
    Get list of products pending synchronization (not yet synced).
    
    **Parameters:**
    - `domain`: The domain name
    
    **Returns:**
    - List of unsynced products with their metadata
    """
    try:
        unsynced = await archiver.get_unsynced_products(domain)
        return {
            "domain": domain,
            "pending_count": len(unsynced),
            "products": unsynced
        }
    except Exception as e:
        logger.error(f"Get pending error: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": "Internal server error"})

# =============================================================================
# LEGACY ENDPOINT (backwards compatibility)
# =============================================================================

@app.post("/archive/{domain}", tags=["Archives"], deprecated=True)
async def trigger_archive_legacy(domain: str):
    """
    [DEPRECATED] Use /archive/delta/{domain} or /archive/full/{domain} instead.
    
    Creates a full archive for backwards compatibility.
    """
    return await create_full_archive(domain)
