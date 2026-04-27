"""Routeur FastAPI pour les actions Albums (visualisation + redownload + delete).

Endpoints :
    GET    /domains/_summary
    GET    /domains/{domain}/products
    POST   /products/{domain}/{id_produit}/redownload
    POST   /images/{domain}/{id_produit}/{filename}/redownload
    DELETE /images/{domain}/{id_produit}/{filename}
    DELETE /products/{domain}/{id_produit}
    DELETE /domains/{domain}
    GET    /jobs/{job_id}

Note : les routes `/sync/{domain}` (POST) et `/sync/{domain}/errors` (GET)
existent déjà dans `main.py` — ne pas les dupliquer ici.
"""

import logging
import os

from fastapi import APIRouter, HTTPException, Query, Response, status
from fastapi.responses import JSONResponse

from services.album_summary import list_domains_with_stats
from services.album_products import list_products, VALID_FILTERS, VALID_SORTS
from services.album_actions import (
    delete_image,
    delete_product,
    redownload_image,
    redownload_product,
    LockTimeoutError,
    ManifestEntryMissingError,
)
from services.album_jobs import start_delete_album_job, get_job

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Albums"])


def _storage_base() -> str:
    """Lit STORAGE_BASE à chaque appel pour rester cohérent avec core.downloader.

    Convention : STORAGE_BASE pointe vers le répertoire racine du stockage,
    avec sous-dossiers `images/` et `archives/`.
    """
    return os.environ.get("STORAGE_BASE", "/app/storage")


def _get_downloader():
    """Singleton Downloader pour les redownloads. Lazy import pour éviter la circulaire."""
    from core.downloader import Downloader
    if not hasattr(_get_downloader, "_inst"):
        _get_downloader._inst = Downloader()
    return _get_downloader._inst


# =============================================================================
# READS
# =============================================================================

@router.get("/domains/_summary")
async def domains_summary():
    return await list_domains_with_stats(_storage_base())


@router.get("/domains/{domain}/products")
async def domain_products(
    domain: str,
    q: str = "",
    filter: str = Query("all"),
    sort: str = Query("updated"),
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
):
    if filter not in VALID_FILTERS:
        raise HTTPException(400, f"filter invalide. Acceptés : {sorted(VALID_FILTERS)}")
    if sort not in VALID_SORTS:
        raise HTTPException(400, f"sort invalide. Acceptés : {sorted(VALID_SORTS)}")
    try:
        return await list_products(
            _storage_base(), domain,
            q=q, filter=filter, sort=sort, page=page, page_size=page_size,
        )
    except FileNotFoundError:
        raise HTTPException(404, f"domaine inconnu : {domain}")


# =============================================================================
# REDOWNLOADS
# =============================================================================

@router.post("/products/{domain}/{id_produit}/redownload")
async def redownload_product_endpoint(domain: str, id_produit: str):
    try:
        return await redownload_product(_storage_base(), domain, id_produit, _get_downloader())
    except FileNotFoundError:
        raise HTTPException(422, "manifest absent ou produit inexistant")
    except LockTimeoutError:
        raise HTTPException(409, "verrou occupé sur ce produit, réessaie")


@router.post("/images/{domain}/{id_produit}/{filename}/redownload")
async def redownload_image_endpoint(domain: str, id_produit: str, filename: str):
    try:
        return await redownload_image(
            _storage_base(), domain, id_produit, filename, _get_downloader()
        )
    except ManifestEntryMissingError:
        raise HTTPException(422, "image inconnue dans le manifest")
    except FileNotFoundError:
        raise HTTPException(404, "produit ou domaine inconnu")
    except LockTimeoutError:
        raise HTTPException(409, "verrou occupé, réessaie")


# =============================================================================
# DELETES
# =============================================================================

@router.delete("/images/{domain}/{id_produit}/{filename}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_image_endpoint(domain: str, id_produit: str, filename: str):
    try:
        await delete_image(_storage_base(), domain, id_produit, filename)
    except FileNotFoundError:
        raise HTTPException(404, "image, produit ou domaine inconnu")
    except LockTimeoutError:
        raise HTTPException(409, "verrou occupé, réessaie")
    return Response(status_code=204)


@router.delete("/products/{domain}/{id_produit}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product_endpoint(domain: str, id_produit: str):
    try:
        await delete_product(_storage_base(), domain, id_produit)
    except FileNotFoundError:
        raise HTTPException(404, "produit ou domaine inconnu")
    except LockTimeoutError:
        raise HTTPException(409, "verrou occupé, réessaie")
    return Response(status_code=204)


@router.delete("/domains/{domain}", status_code=status.HTTP_202_ACCEPTED)
async def delete_album_endpoint(domain: str):
    domain_dir = os.path.join(_storage_base(), "images", domain)
    if not os.path.isdir(domain_dir):
        raise HTTPException(404, f"domaine inconnu : {domain}")
    job = start_delete_album_job(_storage_base(), domain)
    return JSONResponse(
        status_code=202,
        content={**job, "poll_url": f"/jobs/{job['job_id']}"},
    )


# =============================================================================
# JOBS
# =============================================================================

@router.get("/jobs/{job_id}")
async def get_job_endpoint(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(404, "job inconnu")
    return job
