from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import HTTPException as FastAPIHTTPException
from fastapi.responses import JSONResponse

from app.routers import (
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
    yield


app = FastAPI(title="account-service-backend", lifespan=lifespan)
app.include_router(health.router)
app.include_router(jwks.router)
app.include_router(authorize.router)
app.include_router(token.router)
app.include_router(revoke.router)
app.include_router(introspect.router)
app.include_router(userinfo.router)
app.include_router(logout.router)


@app.exception_handler(FastAPIHTTPException)
async def http_exception_handler(_: Request, exc: FastAPIHTTPException):
    if isinstance(exc.detail, dict):
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    return JSONResponse(status_code=exc.status_code, content={"error": str(exc.detail)})
