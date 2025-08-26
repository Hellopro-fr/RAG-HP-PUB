import logging
from dotenv import load_dotenv
import os
from fastapi import APIRouter, FastAPI, Request, status
from fastapi.openapi.utils import get_openapi
from fastapi.middleware.cors import CORSMiddleware
from app.core.credentials import settings
from app.utils.params import params
from app.utils.response import error_response

load_dotenv(dotenv_path=".env")

description = """
API d'embedding [RAG Hellopro] 🚀
"""

os.makedirs(f'{settings.DOCUMENT_ROOT}/logs', exist_ok=True)

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

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    filename=f"{settings.DOCUMENT_ROOT}/logs/app.log",
    filemode="a"
)


@app.exception_handler(Exception)
async def error_handler(request, exc: Exception):
    logging.error(str(exc))
    return error_response(
        "EXCEPTION_ERROR", f"{exc}", status.HTTP_500_INTERNAL_SERVER_ERROR)


for item in params:
    app.include_router(
        item[0],
        prefix=item[1],
        tags=item[2],
        include_in_schema=item[3]
    )


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