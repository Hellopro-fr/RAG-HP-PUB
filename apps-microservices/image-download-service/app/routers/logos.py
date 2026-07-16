"""Routeur FastAPI pour les Logos Fournisseur (chantier logo fournisseur — Task 2).

Endpoints :
    POST   /logos/enqueue          # Trigger download asynchrone (miroir /pages/enqueue)
    GET    /logos/{domaine}        # Contenu manifest_logo.json

Architecture :
    - POST /enqueue publie vers RabbitMQ (data_exchange_logos / new_data.logo)
      via la connexion partagee app.state.rabbitmq_connection (meme pattern que
      app/routers/pages.py).
    - Le GET lit manifest_logo.json depuis STORAGE_BASE/images/{domain}/logo/.
    - LogoConsumer (app/messaging/logo_consumer.py) consomme la queue et appelle
      Downloader.process_logo_download() (app/core/downloader.py), qui delegue le
      traitement logo-safe a process_logo (app/core/image_processor.py, Task 1).
"""

import asyncio
import json
import logging
import os
import re

import aio_pika
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/logos", tags=["Logos"])


# =============================================================================
# SECURITE — VALIDATION DOMAINE (anti path-traversal)
# =============================================================================
# Miroir de app/routers/pages.py::_DOMAIN_RE — meme garde, meme raisonnement :
# les endpoints POST /enqueue n'en ont pas besoin (domaine issu d'un body Pydantic
# valide), seul le GET /{domaine} (parametre URL) doit etre protege.

_DOMAIN_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def _validate_domain(domain: str) -> None:
    if not _DOMAIN_RE.fullmatch(domain):
        raise HTTPException(status_code=400, detail="domaine invalide")


# =============================================================================
# HELPERS INTERNES
# =============================================================================

def _storage_base() -> str:
    """Lit STORAGE_BASE a chaque appel — coherent avec core.downloader."""
    return os.environ.get("STORAGE_BASE", "/app/storage")


def _manifest_logo_path(storage_base: str, domain: str) -> str:
    return os.path.join(storage_base, "images", domain, "logo", "manifest_logo.json")


# =============================================================================
# MODELES
# =============================================================================

class LogoPayload(BaseModel):
    domaine: str = Field(..., description="Domaine fournisseur")
    url_logo: str = Field(..., description="URL absolue du logo source")
    key: str = Field(..., description="Cle d'identification du logo (dedup manifest)")


# =============================================================================
# POST — ENQUEUE
# =============================================================================

@router.post("/enqueue", status_code=202)
async def enqueue_logo(payload: LogoPayload, request: Request):
    """Publie un evenement RabbitMQ vers LogoConsumer pour telechargement async.

    Flow : BO Hellopro -> POST /logos/enqueue -> RabbitMQ
    data_exchange_logos / new_data.logo -> LogoConsumer.
    Miroir exact de enqueue_page_image (app/routers/pages.py).
    """
    connection = getattr(request.app.state, "rabbitmq_connection", None)
    if not connection or connection.is_closed:
        raise HTTPException(503, detail="RabbitMQ unavailable")

    try:
        async with connection.channel() as channel:
            exchange_name = os.environ.get("LOGO_EXCHANGE_NAME", "data_exchange_logos")
            routing_key = os.environ.get("LOGO_ROUTING_KEY", "new_data.logo")
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
    except Exception as exc:
        logger.exception(
            "Erreur publish RabbitMQ pour key=%s domaine=%s: %s",
            payload.key,
            payload.domaine,
            exc,
        )
        raise HTTPException(status_code=503, detail="RabbitMQ publish failed")

    return {
        "status": "accepted",
        "domaine": payload.domaine,
        "key": payload.key,
    }


# =============================================================================
# GET — LECTURE MANIFEST
# =============================================================================

@router.get("/{domain}")
async def get_domain_logos(domain: str):
    """Retourne le contenu de manifest_logo.json pour le domaine.

    Structure : {"logos": [{key, hosted_path, format, width, height,
    content_hash, downloaded_at}, ...], "last_updated": ...}.
    Aucune erreur 404 : domaine sans logo encore traite -> structure vide
    (aligne sur le comportement de GET /pages/{domain}/images).
    """
    _validate_domain(domain)
    manifest = await _load_manifest_logo_file(domain)
    return manifest


# =============================================================================
# HELPER — LECTURE MANIFEST (async, miroir _load_manifest_pages_file)
# =============================================================================

async def _load_manifest_logo_file(domain: str) -> dict:
    """Lit manifest_logo.json pour un domaine ou retourne structure vide.

    Utilise asyncio.to_thread pour ne pas bloquer l'event loop sur I/O sync.
    """
    def _read() -> dict:
        path = _manifest_logo_path(_storage_base(), domain)
        if not os.path.isfile(path):
            return {"logos": [], "last_updated": None}
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {"logos": [], "last_updated": None}
        except Exception:
            logger.exception("Erreur lecture manifest_logo.json pour %s", domain)
            return {"logos": [], "last_updated": None}

    return await asyncio.to_thread(_read)
