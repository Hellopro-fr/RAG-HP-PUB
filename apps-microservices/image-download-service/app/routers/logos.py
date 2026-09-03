"""Routeur FastAPI pour les Logos Fournisseur (chantier logo fournisseur — Task 2).

Endpoints :
    POST   /logos/enqueue           # Trigger download asynchrone (miroir /pages/enqueue)
    GET    /logos/{domaine}         # Contenu manifest_logo.json
    POST   /logos/{domaine}/derive  # Derive d'affichage 200x200 a la demande

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
from typing import List, Optional

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
    """
    Garde du parametre de chemin.

    P19 — LE POINT EST DANS L ALLOWLIST, DONC « .. » LA FRANCHIT. La regex
    ``^[A-Za-z0-9._-]+$`` accepte le point, ce qui est necessaire pour un nom de
    domaine — mais elle accepte donc aussi « . » et « .. ». Mesure :
    ``POST /logos/%2e%2e/derive`` rendait 200 avec ``domain='..'``, et le chemin
    d ecriture resolu sortait de ``images/`` (il tombait dans
    ``{STORAGE_BASE}/logo/d``). Tant que ce parametre ne servait qu a un GET, le
    defaut restait theorique ; il porte maintenant une ECRITURE, donc il faut
    refuser explicitement les composants de traversee. Un vrai nom de domaine
    contient toujours au moins un caractere autre que le point.
    """
    if not _DOMAIN_RE.fullmatch(domain):
        raise HTTPException(status_code=400, detail="domaine invalide")
    if domain.strip(".") == "":
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


class LogoDerivePayload(BaseModel):
    """Corps OPTIONNEL de POST /logos/{domaine}/derive."""

    keys: Optional[List[str]] = Field(
        default=None,
        max_length=200,
        description=(
            "Cles a deriver (manifest_logo.json est une LISTE dedupliquee sur key). "
            "Absent ou vide : toutes les entrees du domaine. Le SERVEUR borne de "
            "toute facon le travail d'un appel (LOGO_DERIVE_MAX_ENTRIES, "
            "LOGO_DERIVE_TIME_BUDGET_S) : ce qui n'a pas ete traite revient dans "
            "`remaining`, avec `truncated: true`."
        ),
    )
    force: bool = Field(
        default=False,
        description="Regenerer meme si le derive est deja complet (bloc manifest ET fichiers).",
    )


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
# POST — DERIVE D'AFFICHAGE A LA DEMANDE
# =============================================================================

@router.post("/{domain}/derive")
async def derive_domain_logos(domain: str, payload: Optional[LogoDerivePayload] = None):
    """Produit (ou confirme) les vignettes d'affichage 200x200 d'un domaine.

    Sert les deux usages du chantier :
      - BACKFILL des domaines dont le logo est deja heberge (le flux ne repassera
        pas dessus) ;
      - VALIDATION (ecran BO, cron 4b, script ponctuel) qui veut la vignette et
        ses metriques tout de suite.

    Synchrone et idempotent : un derive n'est refait que si le bloc du manifest
    manque OU si un fichier de variante manque (``force`` outrepasse les deux).
    La reponse porte les metriques de ``derive_logo`` VERBATIM, pour que le BO
    remplisse ses colonnes sans relire manifest_logo.json.

    ``_validate_domain`` est ici indispensable : contrairement au GET, le
    parametre sert a construire un chemin d'ECRITURE.

    LE TRAVAIL EST BORNE PAR APPEL (nombre d'entrees derivees et budget de
    temps, cf. ``derive_logos_for_domain``) : quand une borne est atteinte, la
    reponse reste 200 et porte ``truncated: true``, ``stop_reason`` et
    ``remaining`` (les cles non traitees) — le pilote de backfill rappelle avec
    ces cles au lieu de deviner.

    Reponse : ``{domaine, recipe, manifest_entries, created[], skipped[],
    failed[], remaining[], truncated, stop_reason, counts{}}``. 200 meme quand
    rien n'a ete cree (le detail est dans ``counts`` et ``failed``), 400 sur
    domaine invalide, 429 quand le processus a deja trop de derivations en cours
    (avec ``Retry-After``), 500 sur defaillance inattendue.
    """
    _validate_domain(domain)

    keys = payload.keys if payload is not None else None
    force = bool(payload.force) if payload is not None else False

    # Lazy import : evite la circulaire router -> core -> router (meme motif que
    # routers/albums.py::_get_downloader).
    from image_download_service.core.downloader import (
        LogoDeriveOverloaded,
        derive_logos_for_domain,
    )

    try:
        return await derive_logos_for_domain(domain, keys=keys, force=force)
    except LogoDeriveOverloaded as exc:
        # Refus HONNETE et immediat. Sans lui, la replica accepte des derivations
        # pyvips en parallele jusqu'a l'OOM-kill — qui ne leve aucune exception
        # Python, donc le message RabbitMQ en vol du consumer n'est jamais
        # acquitte et revient tuer la replica suivante (mesure : 6 derivations
        # simultanees d'un master de 64 Mpx = 1969 Mo, plafond de la replica
        # 2048 Mo).
        logger.warning("Derivation logos saturee domaine=%s : %s", domain, exc)
        raise HTTPException(
            status_code=429,
            detail="derivations saturees, reessayer",
            headers={"Retry-After": "5"},
        )
    except Exception as exc:
        logger.exception("Erreur derivation logos domaine=%s : %s", domain, exc)
        raise HTTPException(status_code=500, detail="derivation logos echouee")


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
