import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from app.api.routes import router
# Import to ensure metric objects are registered with the default registry.
from app.core import metrics  # noqa: F401
from app.core.admission import AdmissionController
from app.middleware.admission import AdmissionMiddleware

from common_utils.redis.cache_service import init_redis_pool, close_redis_pool

# Configuration du logging — INFO pour voir les logs de stratégie proxy, retry, etc.
# Sans cette configuration, Python utilise WARNING par défaut et masque les logs INFO.
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize the shared async Redis pool (common_utils) at startup and
    close it cleanly at shutdown.

    See docs/superpowers/specs/2026-05-22-redis-common-utils-hardening-design.md
    """
    await init_redis_pool()
    yield
    await close_redis_pool()


app = FastAPI(
    title="API Détection Langue Française",
    description=(
        "Détecte si un site web est en français ou dispose d'une version française.\n\n"
        "## Pipeline de détection\n\n"
        "1. **Cache Redis** — Lookup par domaine (TTL 30j ok, 7j nok, 6h transitoire). Bypass via `force_refresh`.\n"
        "2. **Fetch HTML** — Playwright headless via proxy Apify (3 tentatives auto-rotation + fallback variantes URL).\n"
        "3. **Détection challenge** — Identifie Cloudflare, DataDome, Squid, Imperva, pages HTTP 4XX/5XX.\n"
        "4. **Analyse URL** — TLD `.fr` (signal fort), `/fr/` path, `lang=fr` query, sous-domaine `fr.`\n"
        "5. **Balises HTML** — `<html lang>`, `<meta og:locale>`, `<meta http-equiv=content-language>`\n"
        "6. **NLP** — fastText (primaire) + langdetect/langid (cross-check). Cookie consent strippé avant analyse.\n"
        "7. **Liens alternatifs** — hreflang, data-lang, data-gt-lang, liens `/fr/`, options (triés par fiabilité).\n"
        "8. **Matrice de décision** — 9 cas combinant signaux URL/HTML/NLP avec scores de confiance.\n\n"
        "## Modes\n\n"
        "- `simple` — URL + balises HTML uniquement (rapide)\n"
        "- `complete` — + NLP + liens alternatifs (complet)\n"
        "- `first_match` — Batch groupé : arrêt au premier FR par groupe\n"
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

@app.get("/metrics", include_in_schema=False)
async def metrics_endpoint() -> Response:
    """Prometheus metrics exposition endpoint."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


# ─── Admission control ────────────────────────────────────────────────────────
# Two independent in-flight counters:
#   - _prod_admission: gated at the route level by _fetch_with_admission
#     (see app/api/routes.py). Covers /detect and /detect-batch items.
#   - _debug_admission: gated by the AdmissionMiddleware for /detect-debug only.
# Saturation returns 503+Retry-After instead of queueing — protects the
# event loop and Playwright browser pool from overload.
_admission_enabled = os.getenv("ADMISSION_ENABLED", "true").lower() == "true"
_prod_admission = AdmissionController(
    max_slots=int(os.getenv("ADMISSION_MAX_SLOTS", "12"))
)
_debug_admission = AdmissionController(
    max_slots=int(os.getenv("ADMISSION_DEBUG_SLOTS", "2"))
)
app.add_middleware(
    AdmissionMiddleware,
    debug_controller=_debug_admission,
    retry_after_seconds=int(os.getenv("ADMISSION_RETRY_AFTER_SECONDS", "30")),
    enabled=_admission_enabled,
)
logger = logging.getLogger(__name__)
logger.info(
    f"Admission middleware attached: enabled={_admission_enabled}, "
    f"debug={_debug_admission.max_slots} (prod gating moved to route level)"
)


app.include_router(router, prefix="/api/v1")


@app.get("/")
async def root():
    return {
        "message": "API Détection Langue Française",
        "documentation": "/docs",
        "version": "1.0.0"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8999)
