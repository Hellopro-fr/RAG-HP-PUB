"""Routeur FastAPI pour les Pages Images (Chantier D — A4.9).

Endpoints :
    POST   /pages/enqueue                  # Trigger download asynchrone (Phase 3 Hellopro)
    GET    /pages/{domain}/images          # Contenu manifest_pages.json
    GET    /pages/{domain}/status          # Compteurs (downloaded, error, pending)
    GET    /pages/{domain}/errors          # Contenu errors_pages.json
    GET    /pages/{domain}/by-page-type    # Groupement par page_type (manifest filter)
    GET    /pages/{domain}/by-id/{id_image_isi}  # Lookup direct par id_image_isi (Phase 4 polling)

Architecture :
    - POST /enqueue publie vers RabbitMQ (data_exchange_pages_images / new_data.page_image)
      via la connexion partagée app.state.rabbitmq_connection.
    - Les GETs lisent manifest_pages.json et errors_pages.json depuis STORAGE_BASE.
    - _load_manifest_pages_file() est un helper temporaire stub ; la logique de lecture
      réelle (lock NFS + atomic write) sera portée dans un service dédié (T6).

TODO T6 : remplacer _load_manifest_pages_file() par un appel à un service
image_download_service.services.pages_manifest (à créer en T6).
"""

import json
import logging
import os
from collections import defaultdict
from typing import Optional

import aio_pika
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/pages", tags=["Pages"])


# =============================================================================
# HELPERS INTERNES
# =============================================================================

def _storage_base() -> str:
    """Lit STORAGE_BASE à chaque appel — cohérent avec core.downloader."""
    return os.environ.get("STORAGE_BASE", "/app/storage")


def _manifest_pages_path(storage_base: str, domain: str) -> str:
    return os.path.join(storage_base, "images", domain, "manifest_pages.json")


def _errors_pages_path(storage_base: str, domain: str) -> str:
    return os.path.join(storage_base, "images", domain, "errors_pages.json")


# =============================================================================
# MODÈLES
# =============================================================================

class PageImagePayload(BaseModel):
    id_image_isi: int = Field(..., description="ID row image_scrapping_ia")
    domaine: str = Field(..., description="Domaine fournisseur")
    url_image: str = Field(..., description="URL absolue image source")
    url_page_source: str = Field(..., description="URL page où image trouvée")
    page_type: str = Field(..., description="Type page (5 types ferme)")
    alt_text: Optional[str] = ""
    contexte_h1: Optional[str] = ""
    contexte_h2: Optional[str] = ""


# =============================================================================
# POST — ENQUEUE
# =============================================================================

@router.post("/enqueue", status_code=202)
async def enqueue_page_image(payload: PageImagePayload, request: Request):
    """Publie un événement RabbitMQ vers PageImageConsumer pour téléchargement async.

    Flow : Phase 3 Hellopro → POST /pages/enqueue → RabbitMQ
    data_exchange_pages_images / new_data.page_image → PageImageConsumer (T5).
    """
    connection = getattr(request.app.state, "rabbitmq_connection", None)
    if not connection or connection.is_closed:
        raise HTTPException(503, detail="RabbitMQ unavailable")

    async with connection.channel() as channel:
        exchange_name = os.environ.get(
            "PAGE_IMAGE_EXCHANGE_NAME", "data_exchange_pages_images"
        )
        routing_key = os.environ.get("PAGE_IMAGE_ROUTING_KEY", "new_data.page_image")
        exchange = await channel.declare_exchange(
            exchange_name, aio_pika.ExchangeType.TOPIC, durable=True
        )
        await exchange.publish(
            aio_pika.Message(
                body=json.dumps(payload.model_dump()).encode(),
                content_type="application/json",
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            ),
            routing_key=routing_key,
        )

    return {
        "status": "accepted",
        "id_image_isi": payload.id_image_isi,
        "url_image": payload.url_image,
    }


# =============================================================================
# GETs — LECTURE MANIFEST / ERRORS
# =============================================================================

@router.get("/{domain}/images")
async def get_domain_images(domain: str):
    """Retourne le contenu complet de manifest_pages.json pour le domaine.

    Utilisé par Phase 4 polling (batch initial par domaine).
    """
    manifest = _load_manifest_pages_file(domain)
    return manifest


@router.get("/{domain}/status")
async def get_domain_status(domain: str):
    """Compteurs synthétiques : downloaded, error, pending pour le domaine."""
    manifest = _load_manifest_pages_file(domain)
    errors = _load_errors_pages_file(domain)

    downloaded_urls = {e.get("url_source") for e in manifest.get("pages_images", [])}
    error_urls = {e.get("url_image") for e in errors if isinstance(e, dict)}

    return {
        "domain": domain,
        "downloaded": len(downloaded_urls),
        "error": len(error_urls),
        "last_updated": manifest.get("last_updated"),
    }


@router.get("/{domain}/errors")
async def get_domain_errors(domain: str):
    """Retourne le contenu de errors_pages.json pour le domaine.

    Utilisé par Phase 4 polling pour identifier les images en erreur.
    """
    errors = _load_errors_pages_file(domain)
    return {
        "domain": domain,
        "error_count": len(errors),
        "errors": errors,
    }


@router.get("/{domain}/by-page-type")
async def get_images_by_page_type(domain: str):
    """Regroupe les images téléchargées par page_type (filtre manifest_pages).

    Retourne un dict page_type → liste d'entrées manifest.
    """
    manifest = _load_manifest_pages_file(domain)
    groups: dict = defaultdict(list)
    for entry in manifest.get("pages_images", []):
        pt = entry.get("page_type", "unknown")
        groups[pt].append(entry)

    return {
        "domain": domain,
        "total": sum(len(v) for v in groups.values()),
        "by_page_type": dict(groups),
    }


@router.get("/{domain}/by-id/{id_image_isi}")
async def get_image_by_id(domain: str, id_image_isi: int):
    """Lookup direct d'une entrée manifest par id_image_isi.

    Optimisation Phase 4 : évite de re-fetcher le manifest complet pour chaque
    image en timeout retry. Économise bande passante sur gros manifests (>2MB).
    """
    manifest = _load_manifest_pages_file(domain)
    for entry in manifest.get("pages_images", []):
        if entry.get("id_image_isi") == id_image_isi:
            return entry
    raise HTTPException(
        404,
        detail=f"id_image_isi={id_image_isi} introuvable pour domaine {domain}",
    )


# =============================================================================
# HELPERS TEMPORAIRES — TODO T6
# =============================================================================
# TODO T6 : migrer ces deux helpers dans image_download_service.services.pages_manifest
# (service dédié avec lock NFS + atomic write, miroir album_summary / album_products).
# Pour T4, lecture directe JSON sans lock (endpoints GET read-only, cohérent albums.py
# qui lit aussi sans lock pour les GETs).

def _load_manifest_pages_file(domain: str) -> dict:
    """Lit manifest_pages.json pour un domaine ou retourne structure vide.

    TODO T6 : remplacer par image_download_service.services.pages_manifest.load()
    """
    path = _manifest_pages_path(_storage_base(), domain)
    if not os.path.exists(path):
        return {"pages_images": [], "last_updated": None}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.loads(f.read() or "{}")
        return data if isinstance(data, dict) else {"pages_images": [], "last_updated": None}
    except Exception:
        logger.exception("Erreur lecture manifest_pages.json pour %s", domain)
        return {"pages_images": [], "last_updated": None}


def _load_errors_pages_file(domain: str) -> list:
    """Lit errors_pages.json pour un domaine ou retourne liste vide.

    TODO T6 : remplacer par image_download_service.services.pages_manifest.load_errors()
    """
    path = _errors_pages_path(_storage_base(), domain)
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.loads(f.read() or "[]")
        return data if isinstance(data, list) else []
    except Exception:
        logger.exception("Erreur lecture errors_pages.json pour %s", domain)
        return []
