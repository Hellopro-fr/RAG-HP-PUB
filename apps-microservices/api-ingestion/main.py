import logging
from fastapi import APIRouter, FastAPI, Request, status
from fastapi.openapi.utils import get_openapi
from fastapi.middleware.cors import CORSMiddleware
from app.core.credentials import settings
from app.utils.params import params
from app.utils.response import error_response

import logging
import time
import os
import pika

description = """
API pour le projet RAG Hellopro 🚀

## à Venir

Voici les fonctionnalités / Services à venir:

* **Scrapping** (_pas implementé_).
* **Néttoyage (ETL)** (_pas implementé_).
* **Qualification LLM** (_pas implementé_).
* **Vectorisation** (_pas implementé_).
* **Matching** (_pas implementé_).
* **CRUD** (_pas implementé_).
"""


app = FastAPI()

# TODO
# ajout des origines à utiliser pour l'API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs(f'logs', exist_ok=True)
# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    filename="logs/app.log",
    filemode="a"
)

@app.on_event("startup")
def startup_event():
    logging.info("🚀 Ingestion-API: Démarrage et tentative de connexion à RabbitMQ...")
    connection = None
    for i in range(10):
        try:
            params = pika.URLParameters(settings.RABBITMQ_URL)
            connection = pika.BlockingConnection(params)
            app.state.rabbitmq_connection = connection
            app.state.rabbitmq_channel = connection.channel()
            # On s'assure que l'exchange par défaut existe
            app.state.rabbitmq_channel.exchange_declare(exchange='data_exchange', exchange_type='topic', durable=True)
            logging.info("✅ Ingestion-API: Connecté à RabbitMQ.")
            return
        except pika.exceptions.AMQPConnectionError as e:
            logging.warning(f"⏳ Ingestion-API: RabbitMQ n'est pas prêt ({e}). Nouvelle tentative dans {i+1}s...")
            time.sleep(i + 1)
    
    if not connection:
        logging.critical("❌ Ingestion-API: Impossible de se connecter à RabbitMQ après plusieurs tentatives. L'application démarre sans connexion.")
        app.state.rabbitmq_connection = None
        app.state.rabbitmq_channel = None

@app.exception_handler(Exception)
async def error_handler(request, exc: Exception):
    logging.error(str(exc))
    return error_response(
        "EXCEPTION_ERROR", f"{exc}", status.HTTP_500_INTERNAL_SERVER_ERROR)

@app.on_event("shutdown")
def shutdown_event():
    logging.info("🛑 Ingestion-API: Arrêt de l'application...")
    if hasattr(app.state, 'rabbitmq_connection') and app.state.rabbitmq_connection and app.state.rabbitmq_connection.is_open:
        logging.info("Fermeture de la connexion RabbitMQ...")
        app.state.rabbitmq_connection.close()
        logging.info("✅ Connexion RabbitMQ fermée.")


for item in params:
    app.include_router(
        item[0],
        prefix=item[1],
        tags=item[2],
        include_in_schema=item[3]
    )


@app.get("/", tags=["Health Check"])
def read_root():
    return {"status": "ok", "service": "Ingestion API"}

def use_route_names_as_operation_ids(app: FastAPI) -> None:
    for route in app.routes:
        if isinstance(route, APIRouter):
            route.operation_id = route.name


use_route_names_as_operation_ids(app)

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title="API Hellopro",
        description=description,
        version="v1",
        terms_of_service="http://example.com/terms/",
        routes=app.routes,
    )

    openapi_schema["info"]["x-logo"] = {
        # "url": "https://fastapi.tiangolo.com/img/logo-margin/logo-teal.png"
        "url": "statics/plaks.png"
    }
    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi
