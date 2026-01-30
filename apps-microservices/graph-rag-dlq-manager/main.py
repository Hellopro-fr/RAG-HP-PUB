import logging
from fastapi import APIRouter, FastAPI, Request, status
from fastapi.openapi.utils import get_openapi
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.core.config import settings
from app.utils.params import params
from app.services import rabbitmq_client

from starlette.middleware.wsgi import WSGIMiddleware
from common_utils.metrics.prometheus import get_metrics_app


description = """
DLQ Manager API - Gestion des Dead Letter Queues pour le pipeline RAG 🚀

Cette API permet de:
- Visualiser les messages dans les files DLQ
- Filtrer les messages par routing key ou exchange
- Réinjecter les messages dans la file de retry
- Supprimer les messages des files DLQ
"""


app = FastAPI(
    title="DLQ Manager API",
    description=description,
    version="1.0.0",
)

# Mount the metrics app using the WSGI adapter
metrics_app = get_metrics_app()
app.mount("/metrics", WSGIMiddleware(metrics_app))

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


@app.on_event("startup")
async def startup_event():
    logging.info("🚀 DLQ-Manager-API: Démarrage...")
    # The RabbitMQ Management client uses httpx (no persistent connection needed)
    # AMQP connection will be established on-demand when requeuing
    logging.info("✅ DLQ-Manager-API: Prêt à recevoir des requêtes.")


@app.on_event("shutdown")
async def shutdown_event():
    logging.info("🛑 DLQ-Manager-API: Arrêt de l'application...")
    await rabbitmq_client.close()
    logging.info("✅ DLQ-Manager-API: Connexions fermées.")


@app.exception_handler(Exception)
async def error_handler(request: Request, exc: Exception):
    logging.error(str(exc), exc_info=True)
    return JSONResponse(
        content={
            "success": False,
            "message": str(exc),
            "code": "INTERNAL_ERROR",
        },
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


# Register routers
for item in params:
    app.include_router(item[0], prefix=item[1], tags=item[2], include_in_schema=item[3])


@app.get("/", tags=["Health Check"])
def read_root():
    return {"status": "ok", "service": "DLQ Manager API"}


def use_route_names_as_operation_ids(app: FastAPI) -> None:
    for route in app.routes:
        if isinstance(route, APIRouter):
            route.operation_id = route.name


use_route_names_as_operation_ids(app)


def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title="DLQ Manager API",
        description=description,
        version="v1",
        routes=app.routes,
    )
    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi
