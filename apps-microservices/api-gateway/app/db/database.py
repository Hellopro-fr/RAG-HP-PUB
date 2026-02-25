"""
Tortoise-ORM initialisation and teardown helpers for the API Gateway.

Usage (FastAPI lifespan):

    from contextlib import asynccontextmanager
    from app.db.database import init_db, close_db, bootstrap_refresh_tokens

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await init_db()
        await bootstrap_refresh_tokens()
        yield
        await close_db()
"""

import os
import logging

from tortoise import Tortoise

logger = logging.getLogger("db")

# ─── MySQL connection URL built from individual env vars ──────────────────────
_MYSQL_HOST = os.environ.get("MYSQL_HOST", "mysql")
_MYSQL_PORT = os.environ.get("MYSQL_PORT", "3306")
_MYSQL_USER = os.environ.get("MYSQL_USER", "gateway_user")
_MYSQL_PASS = os.environ.get("MYSQL_PASS", "gateway_pass")
_MYSQL_DB = os.environ.get("MYSQL_DB", "gateway_db")

DATABASE_URL = (
    f"mysql://{_MYSQL_USER}:{_MYSQL_PASS}@{_MYSQL_HOST}:{_MYSQL_PORT}/{_MYSQL_DB}"
)

TORTOISE_ORM = {
    "connections": {
        "default": DATABASE_URL,
    },
    "apps": {
        "models": {
            "models": ["app.db.models", "aerich.models"],
            "default_connection": "default",
        },
    },
}


async def init_db() -> None:
    """Initialise Tortoise-ORM and create tables (if they don't exist)."""
    logger.info(
        f"[db] Connecting to MySQL at {_MYSQL_HOST}:{_MYSQL_PORT}/{_MYSQL_DB} ..."
    )
    await Tortoise.init(config=TORTOISE_ORM)
    # generate_schemas is idempotent and safe to call on every startup
    await Tortoise.generate_schemas(safe=True)
    logger.info("[db] Tortoise-ORM ready — schemas applied.")


async def close_db() -> None:
    """Close all Tortoise-ORM connections cleanly."""
    logger.info("[db] Closing Tortoise-ORM connections ...")
    await Tortoise.close_connections()
    logger.info("[db] Connections closed.")


async def bootstrap_refresh_tokens() -> None:
    """
    Auto-create a refresh token for every registered service that doesn't
    already have an active one.

    Called once during startup (lifespan), after init_db().
    """
    from app.core.settings import SERVICE_MAP
    from app.db.models import InfoRefreshToken
    from app.utils.token_service import generate_refresh_token

    if not SERVICE_MAP:
        logger.warning("[db] SERVICE_MAP is empty — no services to bootstrap.")
        return

    for api_path, _url in SERVICE_MAP.items():
        # Derive service name from api_path, e.g. "/dlq-service" → "dlq-service"
        service_name = api_path.lstrip("/")

        # Check if an active refresh token already exists
        existing = await InfoRefreshToken.filter(
            nom_service=service_name,
            est_actif=True,
        ).first()

        if existing:
            logger.info(
                f"[db] Bootstrap: active refresh token already exists for "
                f"service='{service_name}' (id={existing.id}) — skipping."
            )
            continue

        # Create a new refresh token
        token_value = generate_refresh_token(service_name)
        record = await InfoRefreshToken.create(
            nom_service=service_name,
            token=token_value,
            ip_creation="system",
            est_actif=True,
        )
        logger.info(
            f"[db] Bootstrap: created refresh token for service='{service_name}' "
            f"(id={record.id})"
        )
