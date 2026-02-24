import os
import asyncio
import logging
import json
import shutil
import time
import aio_pika
from typing import List, Optional
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from contextlib import asynccontextmanager

# Importer les modules locaux
from image_download_service.messaging.consumer import Consumer
from image_download_service.core.archiver import Archiver
from image_download_service.core.metrics import (
    REPLICA_ID, REGISTRY, get_metrics, get_content_type,
    DISK_USAGE_BYTES, DISK_TOTAL_BYTES, DISK_FREE_BYTES,
    DOMAIN_DISK_USAGE_BYTES, PRODUCTS_PER_DOMAIN, IMAGES_PER_DOMAIN,
    UNSYNCED_PRODUCTS_PER_DOMAIN, SERVICE_UPTIME,
)
from image_download_service.core.event_store import event_store

# Configuration du logging uniforme
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

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

# Service start time for uptime tracking
SERVICE_START_TIME = time.monotonic()
STORAGE_BASE = "/app/storage"


async def connect_rabbitmq() -> aio_pika.RobustConnection:
    """
    Établit une connexion RobustConnection à RabbitMQ.
    RobustConnection gère automatiquement les reconnexions.
    """
    rabbitmq_url = os.environ.get("RABBITMQ_URL", "amqp://user:password@localhost:5672/")
    
    max_retries = 10
    retry_delay = 5
    
    for attempt in range(max_retries):
        try:
            logger.info(f"🔄 Connexion à RabbitMQ (tentative {attempt + 1}/{max_retries})...")
            connection = await aio_pika.connect_robust(
                rabbitmq_url,
                client_properties={"connection_name": "image-download-service"}
            )
            logger.info("✅ Connecté à RabbitMQ avec RobustConnection!")
            return connection
        except Exception as e:
            logger.warning(f"❌ Échec de connexion: {e}. Nouvelle tentative dans {retry_delay}s...")
            await asyncio.sleep(retry_delay)
    
    raise Exception(f"❌ Impossible de se connecter à RabbitMQ après {max_retries} tentatives.")


async def _periodic_metrics_updater():
    """Background task to update periodic gauge metrics (disk, domains)."""
    while True:
        try:
            # Disk usage
            if os.path.exists(STORAGE_BASE):
                disk = shutil.disk_usage(STORAGE_BASE)
                DISK_TOTAL_BYTES.labels(replica_id=REPLICA_ID).set(disk.total)
                DISK_FREE_BYTES.labels(replica_id=REPLICA_ID).set(disk.free)
                DISK_USAGE_BYTES.labels(replica_id=REPLICA_ID).set(disk.used)
            
            # Uptime
            SERVICE_UPTIME.labels(replica_id=REPLICA_ID).set(time.monotonic() - SERVICE_START_TIME)
            
            # Per-domain metrics from manifests
            images_base = os.path.join(STORAGE_BASE, "images")
            if os.path.exists(images_base):
                for domain in os.listdir(images_base):
                    domain_path = os.path.join(images_base, domain)
                    if not os.path.isdir(domain_path):
                        continue
                    
                    # Domain disk usage (faster estimate using du-like walk)
                    try:
                        total_size = 0
                        for dirpath, dirnames, filenames in os.walk(domain_path):
                            for f in filenames:
                                fp = os.path.join(dirpath, f)
                                if os.path.isfile(fp):
                                    total_size += os.path.getsize(fp)
                        DOMAIN_DISK_USAGE_BYTES.labels(replica_id=REPLICA_ID, domain=domain).set(total_size)
                    except Exception:
                        pass
                    
                    # Manifest-based metrics
                    manifest_path = os.path.join(domain_path, "manifest.json")
                    if os.path.exists(manifest_path):
                        try:
                            with open(manifest_path, 'r') as f:
                                manifest = json.loads(f.read())
                            products = manifest.get("products", [])
                            PRODUCTS_PER_DOMAIN.labels(replica_id=REPLICA_ID, domain=domain).set(len(products))
                            total_images = sum(len(p.get("images", [])) for p in products)
                            IMAGES_PER_DOMAIN.labels(replica_id=REPLICA_ID, domain=domain).set(total_images)
                            unsynced = sum(1 for p in products if not p.get("synced", False))
                            UNSYNCED_PRODUCTS_PER_DOMAIN.labels(replica_id=REPLICA_ID, domain=domain).set(unsynced)
                        except Exception:
                            pass
            
            await asyncio.sleep(30)  # Update every 30 seconds
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Metrics updater error: {e}")
            await asyncio.sleep(30)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("🚀 Image-Download-Service: Démarrage...")
    
    # Connect the event store
    await event_store.connect()
    
    try:
        # Établir la connexion RabbitMQ
        app.state.rabbitmq_connection = await connect_rabbitmq()
        
        # Initialiser le Consumer avec la connexion (Publisher supprimé - non utilisé)
        app.state.consumer = Consumer(app.state.rabbitmq_connection)
        
        # Démarrer le consumer en tâche de fond
        app.state.consumer_task = asyncio.create_task(app.state.consumer.start_consuming())
        logger.info("✅ Consumer démarré en tâche de fond.")
        
    except Exception as e:
        logger.error(f"❌ Erreur lors du démarrage: {e}")
        # Continue sans RabbitMQ - l'API REST fonctionnera toujours
    
    # Start the periodic metrics updater
    app.state.metrics_task = asyncio.create_task(_periodic_metrics_updater())
    
    # Update initial replica status
    await event_store.update_replica_status(REPLICA_ID, {
        "state": "idle",
        "started_at": __import__("datetime").datetime.now().isoformat(),
    })
    
    yield
    
    # Shutdown
    logger.info("🛑 Image-Download-Service: Arrêt...")
    
    # Cancel metrics updater
    if hasattr(app.state, 'metrics_task'):
        app.state.metrics_task.cancel()
        try:
            await app.state.metrics_task
        except asyncio.CancelledError:
            pass
    
    # Annuler la tâche consumer
    if hasattr(app.state, 'consumer_task'):
        app.state.consumer_task.cancel()
        try:
            await app.state.consumer_task
        except asyncio.CancelledError:
            pass
    
    # Fermer la connexion RabbitMQ
    if hasattr(app.state, 'rabbitmq_connection') and app.state.rabbitmq_connection:
        await app.state.rabbitmq_connection.close()
        logger.info("✅ Connexion RabbitMQ fermée.")
    
    # Close event store
    await event_store.close()

app = FastAPI(
    title="Image Download Service",
    description="Service pour télécharger, traiter et archiver les images de produits avec support de synchronisation incrémentale",
    version="2.0.0",
    lifespan=lifespan,
    openapi_tags=[
        {
            "name": "Health",
            "description": "Vérifications de santé du service",
        },
        {
            "name": "Archives",
            "description": "Créer et télécharger des archives d'images (full ou delta)",
        },
        {
            "name": "Sync",
            "description": "Statut et gestion de la synchronisation",
        },
        {
            "name": "Domains",
            "description": "Gestion et listing des domaines",
        },
        {
            "name": "Monitoring",
            "description": "Métriques, événements et monitoring temps réel",
        }
    ]
)

# CORS for the monitoring dashboard
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

archiver = Archiver()

# =============================================================================
# HEALTH
# =============================================================================

@app.get("/health", tags=["Health"])
def health_check():
    """Health check endpoint for the service."""
    return {
        "status": "ok",
        "service": "image-download-service",
        "version": "2.0.0",
        "replica_id": REPLICA_ID,
    }

# =============================================================================
# MONITORING — Prometheus + SSE + Stats
# =============================================================================

@app.get("/metrics", tags=["Monitoring"], include_in_schema=False)
async def prometheus_metrics():
    """Prometheus metrics endpoint (scraped by Prometheus)."""
    return Response(
        content=get_metrics(),
        media_type=get_content_type(),
    )

@app.get("/events/stream", tags=["Monitoring"])
async def sse_event_stream(request: Request):
    """
    Server-Sent Events stream for real-time monitoring.
    Connect via EventSource in the browser for live updates.
    """
    async def event_generator():
        try:
            async for event in event_store.stream_events():
                if await request.is_disconnected():
                    break
                data = json.dumps(event, ensure_ascii=False)
                yield f"data: {data}\n\n"
        except asyncio.CancelledError:
            pass
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

@app.get("/stats/overview", tags=["Monitoring"])
async def stats_overview():
    """
    Complete overview snapshot for the dashboard.
    Returns disk, replicas, active downloads, and domain info.
    """
    # Disk info
    disk_info = {}
    if os.path.exists(STORAGE_BASE):
        disk = shutil.disk_usage(STORAGE_BASE)
        disk_info = {
            "total_bytes": disk.total,
            "used_bytes": disk.used,
            "free_bytes": disk.free,
            "used_percent": round((disk.used / disk.total) * 100, 2) if disk.total > 0 else 0,
        }
    
    # Replicas
    replicas = await event_store.get_all_replicas()
    
    # Active downloads
    active_downloads = await event_store.get_active_downloads()
    
    # Domains from archiver
    domains = await archiver.list_domains()
    domain_stats = []
    for domain in domains:
        status = await archiver.get_sync_status(domain)
        domain_stats.append(status)
    
    return {
        "replica_id": REPLICA_ID,
        "uptime_seconds": round(time.monotonic() - SERVICE_START_TIME, 2),
        "disk": disk_info,
        "replicas": replicas,
        "active_downloads": active_downloads,
        "domains": domain_stats,
        "domain_count": len(domains),
    }

@app.get("/stats/replicas", tags=["Monitoring"])
async def stats_replicas():
    """Get status of all replicas."""
    replicas = await event_store.get_all_replicas()
    active_downloads = await event_store.get_active_downloads()
    return {
        "replicas": replicas,
        "active_downloads": active_downloads,
        "count": len(replicas),
    }

@app.get("/stats/domains", tags=["Monitoring"])
async def stats_domains():
    """Detailed domain statistics for the dashboard."""
    domains = await archiver.list_domains()
    result = []
    
    images_base = os.path.join(STORAGE_BASE, "images")
    
    for domain in domains:
        status = await archiver.get_sync_status(domain)
        
        # Calculate disk usage for this domain
        domain_path = os.path.join(images_base, domain)
        disk_usage = 0
        file_count = 0
        try:
            for dirpath, dirnames, filenames in os.walk(domain_path):
                for f in filenames:
                    fp = os.path.join(dirpath, f)
                    if os.path.isfile(fp):
                        disk_usage += os.path.getsize(fp)
                        file_count += 1
        except Exception:
            pass
        
        status["disk_usage_bytes"] = disk_usage
        status["file_count"] = file_count
        result.append(status)
    
    return {
        "domains": result,
        "count": len(result),
    }

@app.get("/stats/errors", tags=["Monitoring"])
async def stats_errors(count: int = 100):
    """Get recent error events."""
    from image_download_service.core.event_store import STREAM_ERRORS
    errors = await event_store.read_recent_events(stream=STREAM_ERRORS, count=count)
    return {
        "errors": errors,
        "count": len(errors),
    }

@app.get("/stats/events", tags=["Monitoring"])
async def stats_events(count: int = 100):
    """Get recent events (all types)."""
    events = await event_store.read_recent_events(count=count)
    return {
        "events": events,
        "count": len(events),
    }

@app.get("/stats/disk", tags=["Monitoring"])
async def stats_disk():
    """Detailed disk usage statistics."""
    disk_info = {}
    if os.path.exists(STORAGE_BASE):
        disk = shutil.disk_usage(STORAGE_BASE)
        disk_info = {
            "total_bytes": disk.total,
            "used_bytes": disk.used,
            "free_bytes": disk.free,
            "used_percent": round((disk.used / disk.total) * 100, 2) if disk.total > 0 else 0,
        }
    
    # Per-domain breakdown
    images_base = os.path.join(STORAGE_BASE, "images")
    domain_usage = []
    if os.path.exists(images_base):
        for domain in os.listdir(images_base):
            domain_path = os.path.join(images_base, domain)
            if not os.path.isdir(domain_path):
                continue
            
            total_size = 0
            file_count = 0
            try:
                for dirpath, dirnames, filenames in os.walk(domain_path):
                    for f in filenames:
                        fp = os.path.join(dirpath, f)
                        if os.path.isfile(fp):
                            total_size += os.path.getsize(fp)
                            file_count += 1
            except Exception:
                pass
            
            domain_usage.append({
                "domain": domain,
                "size_bytes": total_size,
                "file_count": file_count,
            })
    
    # Archives
    archives_base = os.path.join(STORAGE_BASE, "archives")
    archives_size = 0
    archives_count = 0
    if os.path.exists(archives_base):
        for f in os.listdir(archives_base):
            fp = os.path.join(archives_base, f)
            if os.path.isfile(fp):
                archives_size += os.path.getsize(fp)
                archives_count += 1
    
    disk_info["archives_size_bytes"] = archives_size
    disk_info["archives_count"] = archives_count
    
    # Sort by size descending
    domain_usage.sort(key=lambda x: x["size_bytes"], reverse=True)
    
    return {
        "disk": disk_info,
        "domains": domain_usage,
    }

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
        print(f"Delta archive error: {e}")
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
        print(f"Full archive error: {e}")
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
        print(f"Cleanup error: {e}")
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
        print(f"Sync error: {e}")
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
        print(f"Get pending error: {e}")
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
