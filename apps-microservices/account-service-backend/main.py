from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.routers import health, jwks


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield


app = FastAPI(title="account-service-backend", lifespan=lifespan)
app.include_router(health.router)
app.include_router(jwks.router)
