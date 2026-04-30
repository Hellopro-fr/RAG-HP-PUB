from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import HTTPException as FastAPIHTTPException
from fastapi.responses import JSONResponse
from tortoise.contrib.fastapi import register_tortoise

from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.core.jwt_keys import ensure_signing_key
from app.core.settings import get_settings
from app.db.database import build_tortoise_config
from app.middleware import RequestIdMiddleware
from app.rate_limit import limiter
from app.routers import (
    admin_clients,
    authorize,
    health,
    introspect,
    jwks,
    logout,
    revoke,
    token,
    userinfo,
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # register_tortoise creates the TortoiseContext for every request below.
    # This lifespan runs inside that context (per register_tortoise docs),
    # so we can ensure the signing key here.
    settings = get_settings()
    await ensure_signing_key(encryption_key=settings.JWT_KEY_ENCRYPTION_KEY)
    yield


app = FastAPI(title="account-service-backend", lifespan=lifespan)
register_tortoise(
    app,
    config=build_tortoise_config(get_settings().database_url),
    generate_schemas=True,
    add_exception_handlers=True,
)
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(RequestIdMiddleware)


@app.exception_handler(RateLimitExceeded)
async def _rate_limit_handler(_: Request, exc: RateLimitExceeded):
    return JSONResponse(status_code=429, content={"error": "rate_limited"})
app.include_router(health.router)
app.include_router(jwks.router)
app.include_router(authorize.router)
app.include_router(token.router)
app.include_router(revoke.router)
app.include_router(introspect.router)
app.include_router(userinfo.router)
app.include_router(logout.router)
app.include_router(admin_clients.router)


@app.exception_handler(FastAPIHTTPException)
async def http_exception_handler(_: Request, exc: FastAPIHTTPException):
    if isinstance(exc.detail, dict):
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    return JSONResponse(status_code=exc.status_code, content={"error": str(exc.detail)})
