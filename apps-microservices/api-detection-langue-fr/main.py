import asyncio
import logging
import os
from fastapi import FastAPI, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from app.api.routes import router, _run_batch_core, _MIN_PROBE_S
# Import to ensure metric objects are registered with the default registry.
from app.core import metrics  # noqa: F401
from app.core.admission import AdmissionController
from app.middleware.admission import AdmissionMiddleware
from contextlib import asynccontextmanager
from app.core.config import settings as _settings
from app.core.async_jobs import JobStore, JobManager
from common_utils.redis import cache_service
from common_utils.redis.cache_service import init_redis_pool, close_redis_pool
from playwright.async_api import Error as PlaywrightError
from app.core.metrics import ORPHANED_PROTOCOL_FUTURES

# Configuration du logging — INFO pour voir les logs de stratégie proxy, retry, etc.
# Sans cette configuration, Python utilise WARNING par défaut et masque les logs INFO.
# force=True : l'import de cache_service ci-dessus exécute son propre
# basicConfig au niveau module — sans force, celui-ci serait un no-op silencieux
# (perte des timestamps et noms de logger).
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    force=True,
)

# Le pool cache_service est init une seule fois au startup ; si Redis était
# injoignable à cet instant, redis_client reste None pour toujours (dégradation
# permanente : cache invisible + submit async 503 non-retryable). Les anciens
# clients lazy se reconnectaient d'eux-mêmes — cette boucle restaure ce
# comportement. init_redis_pool est idempotent (ping-guard) donc sans coût
# quand le pool est sain.
_REDIS_RECONNECT_INTERVAL_S = int(os.getenv("REDIS_RECONNECT_INTERVAL_S", "30"))

# Référence capturée à l'import : des tests patchent asyncio.sleep au niveau
# module (via app.api.routes.asyncio) — sans capture, la boucle de reconnexion
# deviendrait une boucle chaude pendant ces tests.
_sleep = asyncio.sleep


async def _redis_reconnect_loop() -> None:
    while True:
        await _sleep(_REDIS_RECONNECT_INTERVAL_S)
        # Pas de retry si REDIS_URL n'est pas configuré : rien à reconnecter,
        # et init_redis_pool loggue un CRITICAL à chaque appel sans URL.
        if cache_service.redis_client is None and os.getenv("REDIS_URL"):
            await init_redis_pool()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Footgun guard: a budget strictly between 0 (explicit kill-switch, silent
    # by design) and _MIN_PROBE_S disables the URL-variant rescue in practice
    # (every variant sees remaining < _MIN_PROBE_S on the very first check and
    # bails before probing) WITHOUT the operator ever being told — the only
    # meaningful settings are 0 (off) or >= _MIN_PROBE_S (on). Logged once at
    # startup, not inside _variant_rescue (which would log once per item).
    _rescue_budget = _settings.VARIANT_RESCUE_BUDGET_S
    if 0 < _rescue_budget < _MIN_PROBE_S:
        logging.getLogger(__name__).warning(
            f"VARIANT_RESCUE_BUDGET_S={_rescue_budget} < _MIN_PROBE_S={_MIN_PROBE_S} "
            "— le rattrapage par variante d'URL ne pourra jamais sonder une "
            "seule variante à ce réglage (inerte, silencieusement). Mettre "
            f"0 pour désactiver explicitement, ou >= {_MIN_PROBE_S} pour qu'il "
            "agisse réellement."
        )
    # cache_service reads REDIS_URL/SERVICE_NAME from the process env; bridge
    # the pydantic-settings value so a .env-file-only config keeps working,
    # and default the Redis client name for non-compose runs (bare uvicorn
    # would otherwise register as 'crawler-py', the cache_service fallback).
    if _settings.REDIS_URL:
        os.environ.setdefault("REDIS_URL", _settings.REDIS_URL)
    os.environ.setdefault("SERVICE_NAME", "api-detection-langue-fr-service")
    await init_redis_pool()
    reconnect_task = asyncio.create_task(_redis_reconnect_loop())
    store = JobStore()
    app.state.job_manager = JobManager(store=store, batch_runner=_run_batch_core, settings=_settings)
    logging.getLogger(__name__).info("Async JobManager initialised (lifespan startup)")
    asyncio.get_running_loop().set_exception_handler(_handle_loop_exception)
    logging.getLogger(__name__).info("Loop exception handler installed (orphaned Playwright callbacks)")
    yield
    reconnect_task.cancel()
    await asyncio.gather(reconnect_task, return_exceptions=True)
    await app.state.job_manager.shutdown()
    await close_redis_pool()
    logging.getLogger(__name__).info("Async JobManager shut down (lifespan shutdown)")


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


def _handle_loop_exception(loop, context) -> None:
    """Drain orphaned Playwright protocol callbacks; report everything else.

    A cancelled scrape (the 300s per-item wait_for, or any caller cancel) leaves
    `page.goto`'s protocol callback pending AND uncancelled, because asyncio.wait
    inside Playwright's _inner_send does not cancel what it awaited. When the
    browser is then closed, Connection.cleanup() sets TargetClosedError on that
    callback — and nobody can retrieve it, since the awaiting frame is gone.
    Playwright already suppresses the two sibling cases (no_reply, and
    already-cancelled) with the comment "To prevent 'Future exception was never
    retrieved'"; this completes that suppression for the third.
    Upstream: playwright-python#2163, unchanged through v1.62.0.

    NARROW on three axes — a Playwright error, named TargetClosedError, with a
    future that is a bare Future and not a Task. That third axis is the real
    discriminator: Task.__del__ (asyncio/tasks.py) only special-cases a Task
    destroyed while still pending; the never-retrieved-exception case falls
    through to Future.__del__, which puts the Task itself under the 'future'
    key and never sets a 'task' key (asyncio/base_events.py's own comment:
    "Task is a subclass of Future, and sometimes the 'future' key holds a
    Task"). So a TargetClosedError raised on a live awaited path surfaces here
    as a Task under 'future' and still reaches the default handler; only a
    bare, orphaned Future is drained.

    Matched by class NAME on purpose: TargetClosedError is not exported by
    playwright.async_api (only Error is), and importing it from
    playwright._impl._errors would tie us to a private module that the pending
    1.58 -> 1.60 upgrade could move.
    """
    exc = context.get("exception")
    if (
        isinstance(exc, PlaywrightError)
        and type(exc).__name__ == "TargetClosedError"
        and context.get("future") is not None
        # Task.__del__ falls through to Future.__del__ for the never-retrieved
        # case, which puts the Task under the 'future' key and never sets
        # 'task' (see asyncio/base_events.py's own comment). So the real
        # discriminator is bare-Future vs Task: an orphaned protocol callback
        # is a plain Future, whereas a Task that dropped an exception is one we
        # still want reported.
        and not isinstance(context.get("future"), asyncio.Task)
    ):
        ORPHANED_PROTOCOL_FUTURES.inc()
        logger.debug(f"orphaned Playwright protocol callback drained: {exc!r}")
        return
    loop.default_exception_handler(context)


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
