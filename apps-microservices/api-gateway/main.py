from fastapi import (
    FastAPI,
    Request,
    WebSocket,
    WebSocketDisconnect,
    Depends,
    HTTPException,
    status,
)
from fastapi.responses import JSONResponse
from fastapi.openapi.utils import get_openapi
from fastapi.responses import Response
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.core.settings import settings, SERVICE_MAP
from app.core.auth import DocsAuthMiddleware
from app.routers.login import router as login_router
from starlette.middleware.sessions import SessionMiddleware
import httpx
import websockets
import logging
import asyncio
import os

app = FastAPI(
    title="API Gateway",
    docs_url=None,  # disable default docs
    redoc_url=None,
    openapi_url=None,
)

# ─── Middleware stack (order matters: SessionMiddleware first, then DocsAuthMiddleware) ─
app.add_middleware(DocsAuthMiddleware)
app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ.get("JWT_SECRET", "changeme-session-secret"),
)

# ─── Include login router ──────────────────────────────────────────────────────
app.include_router(login_router)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

EXCLUDED_HEADERS = {"host", "content-length", "transfer-encoding", "connection"}

# ─── OAuth2 Bearer Token for API consumers ─────────────────────────────────────
OAUTH2_API_KEY = os.getenv("OAUTH2_API_KEY", "changeme-default-api-key")
http_bearer = HTTPBearer(auto_error=True)


async def verify_api_token(
    credentials: HTTPAuthorizationCredentials = Depends(http_bearer),
):
    """
    Dependency for API proxy routes.
    Validates the Bearer token against the OAUTH2_API_KEY env var.
    """
    if credentials.credentials != OAUTH2_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired API token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return credentials.credentials


@app.api_route(
    "/{service}/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    include_in_schema=False,
)
async def proxy(
    service: str, path: str, request: Request, _token: str = Depends(verify_api_token)
):
    base_url = SERVICE_MAP.get(f"/{service}")
    if not base_url:
        return JSONResponse(status_code=404, content={"detail": "Service not found"})

    # 1. Construire l'URL de destination en conservant les query parameters
    target_url = f"{base_url}/{path}"
    if request.query_params:
        target_url += "?" + str(request.query_params)

    # 2. Propager les headers du client, en excluant ceux qui sont spécifiques à la connexion
    headers = {
        name: value
        for name, value in request.headers.items()
        if name.lower() not in EXCLUDED_HEADERS
    }

    # 3. Lire le corps de la requête
    body = await request.body()

    # 4. Utiliser un client httpx pour faire la requête au service final
    async with httpx.AsyncClient() as client:
        try:
            response = await client.request(
                request.method,
                target_url,
                headers=headers,
                content=body,
                # timeout=30.0  # Il est toujours bon de mettre un timeout
                timeout=None,  # pour la classification des produits
            )
        except httpx.RequestError as e:
            # Gérer les erreurs de connexion au service (service down, etc.)
            logger.error(f"Impossible de contacter le service {service}: {e}")
            return JSONResponse(
                status_code=503,  # Service Unavailable
                content={"detail": f"Le service '{service}' est indisponible."},
            )

    # 5. Renvoyer la réponse du service au client
    # On propage également les headers de la réponse du service
    response_headers = {
        name: value
        for name, value in response.headers.items()
        if name.lower() not in EXCLUDED_HEADERS
    }

    response_headers["X-Content-Type-Options"] = "nosniff"
    response_headers["X-Frame-Options"] = "DENY"
    response_headers["Strict-Transport-Security"] = (
        "max-age=31536000; includeSubDomains"
    )

    return Response(
        content=response.content,
        status_code=response.status_code,
        headers=response_headers,
        media_type=response.headers.get("content-type"),
    )


@app.websocket("/{service}/{path:path}")
async def websocket_proxy(service: str, path: str, websocket: WebSocket):
    base_url = SERVICE_MAP.get(f"/{service}")
    if not base_url:
        logger.warning(f"[GW] Service '{service}' non trouvé. Fermeture WS.")
        await websocket.close(code=1008)
        return

    ws_url = base_url.replace("http://", "ws://").replace("https://", "wss://")
    target_url = f"{ws_url}/{path}"

    if websocket.url.query:
        target_url += "?" + websocket.url.query

    logger.info(f"[GW] Connexion client acceptée pour {websocket.url.path}")
    await websocket.accept()

    EXCLUDED_WS_HEADERS = {
        "connection",
        "upgrade",
        "host",
        "sec-websocket-key",
        "sec-websocket-version",
        "sec-websocket-protocol",
        "sec-websocket-extensions",
    }

    try:
        logger.info(f"[GW] Tentative de connexion au backend : {target_url}")

        forwarded_headers = [
            (name, value)
            for name, value in websocket.headers.items()
            if name.lower() not in EXCLUDED_WS_HEADERS
        ]

        async with websockets.connect(
            target_url, extra_headers=forwarded_headers
        ) as backend_ws:
            logger.info("[GW] Connexion au backend réussie. Démarrage du relais.")

            async def forward_to_backend():
                try:
                    while True:
                        data = await websocket.receive_text()
                        # logger.info(f"[GW] Client -> Backend: {data[:200]}...")
                        await backend_ws.send(data)
                except WebSocketDisconnect:
                    logger.info("[GW] Le client s'est déconnecté.")

            async def forward_to_client():
                try:
                    while True:
                        data = await backend_ws.recv()
                        # logger.info(f"[GW] Backend -> Client: {data[:200]}...")
                        await websocket.send_text(data)
                except websockets.exceptions.ConnectionClosed:
                    logger.info("[GW] Le backend a fermé la connexion.")

            client_task = asyncio.create_task(forward_to_backend())
            backend_task = asyncio.create_task(forward_to_client())
            done, pending = await asyncio.wait(
                [client_task, backend_task], return_when=asyncio.FIRST_COMPLETED
            )
            for task in pending:
                task.cancel()

    except websockets.exceptions.InvalidStatusCode as e:
        logger.error(
            f"[GW] ERREUR: Le backend a refusé la connexion WebSocket avec le statut {e.status_code}"
        )
    except Exception as e:
        logger.error(
            f"[GW] ERREUR inattendue dans le proxy WebSocket : {e}", exc_info=True
        )
    finally:
        # Laisser le framework gérer la fermeture de la connexion client.
        # Le `async with` gère déjà la fermeture de la connexion backend.
        logger.info("[GW] Nettoyage et fin du proxy pour cette connexion.")
        # --- LIGNE SUPPRIMÉE ---
        # await websocket.close()


# Combine all OpenAPI schemas
@app.get("/openapi.json", include_in_schema=False)
async def custom_openapi():
    openapi = get_openapi(
        title="API Gateway",
        version="1.0.0",
        description="Combined schema of all microservices",
        routes=app.routes,
    )

    # Tracker pour détecter les collisions de schémas
    schema_tracker = {}  # {schema_name: [service_prefix1, service_prefix2, ...]}

    async with httpx.AsyncClient() as client:
        # Premier passage : détecter les collisions
        service_schemas = {}  # {prefix: sub_openapi}
        for prefix, url in SERVICE_MAP.items():
            try:
                r = await client.get(f"{url}/openapi.json")
                r.raise_for_status()
                sub_openapi = r.json()
                service_schemas[prefix] = sub_openapi

                # Tracker les schémas de ce service
                if (
                    "components" in sub_openapi
                    and "schemas" in sub_openapi["components"]
                ):
                    for schema_name in sub_openapi["components"]["schemas"].keys():
                        if schema_name not in schema_tracker:
                            schema_tracker[schema_name] = []
                        schema_tracker[schema_name].append(prefix)

            except Exception as e:
                print(f"Failed to fetch schema from {url}: {e}")

        # Identifier les schémas en collision (présents dans plusieurs services)
        conflicting_schemas = {
            name for name, prefixes in schema_tracker.items() if len(prefixes) > 1
        }

        # Deuxième passage : merger avec préfixe seulement si collision
        for prefix, sub_openapi in service_schemas.items():
            # Créer un préfixe unique pour les schémas basé sur le service
            # Ex: /classification-service -> Classification, /classification-v2-service -> ClassificationV2
            schema_prefix = (
                prefix.strip("/")
                .replace("-service", "")
                .replace("-", "_")
                .title()
                .replace("_", "")
            )

            # Fonction pour remplacer les références de schémas
            def prefix_refs(obj, prefix_to_use, schemas_to_prefix):
                """Préfixe récursivement les références $ref uniquement pour les schémas en collision"""
                if isinstance(obj, dict):
                    new_obj = {}
                    for k, v in obj.items():
                        if (
                            k == "$ref"
                            and isinstance(v, str)
                            and "#/components/schemas/" in v
                        ):
                            schema_name = v.split("/")[-1]
                            # Préfixer seulement si ce schéma est en collision
                            if schema_name in schemas_to_prefix:
                                new_obj[k] = (
                                    f"#/components/schemas/{prefix_to_use}{schema_name}"
                                )
                            else:
                                new_obj[k] = v
                        else:
                            new_obj[k] = prefix_refs(
                                v, prefix_to_use, schemas_to_prefix
                            )
                    return new_obj
                elif isinstance(obj, list):
                    return [
                        prefix_refs(item, prefix_to_use, schemas_to_prefix)
                        for item in obj
                    ]
                else:
                    return obj

            # Préfixer les références dans les paths (seulement pour schémas en collision)
            prefixed_paths = prefix_refs(
                sub_openapi.get("paths", {}), schema_prefix, conflicting_schemas
            )

            # Merge paths with prefix
            for path, path_data in prefixed_paths.items():
                # Préfixer les operationId pour éviter les collisions dans Swagger UI
                for method in [
                    "get",
                    "post",
                    "put",
                    "delete",
                    "patch",
                    "options",
                    "head",
                    "trace",
                ]:
                    if method in path_data and "operationId" in path_data[method]:
                        original_operation_id = path_data[method]["operationId"]
                        # Ajouter le préfixe du service à l'operationId
                        # Ex: classify_single_product -> classification_v2_classify_single_product
                        service_name = (
                            prefix.strip("/").replace("-service", "").replace("-", "_")
                        )
                        path_data[method][
                            "operationId"
                        ] = f"{service_name}_{original_operation_id}"

                # Pas besoin de définir un server spécifique par path car le path complet
                # inclut déjà le préfixe du service (/classification-v2-service/...)
                # Swagger UI utilisera le serveur racine "/" par défaut
                openapi["paths"][f"{prefix}{path}"] = path_data

            # Merge components (schemas, responses, parameters, etc.)
            if "components" in sub_openapi:
                if "components" not in openapi:
                    openapi["components"] = {}

                for comp_type, comp_dict in sub_openapi["components"].items():
                    if comp_type not in openapi["components"]:
                        openapi["components"][comp_type] = {}

                    for key, val in comp_dict.items():
                        # Préfixer seulement si ce schéma est en collision
                        if comp_type == "schemas" and key in conflicting_schemas:
                            prefixed_key = f"{schema_prefix}{key}"
                            prefixed_val = prefix_refs(
                                val, schema_prefix, conflicting_schemas
                            )
                            openapi["components"][comp_type][
                                prefixed_key
                            ] = prefixed_val
                        else:
                            # Pas de collision, garder le nom original
                            if key not in openapi["components"][comp_type]:
                                openapi["components"][comp_type][key] = val

    return JSONResponse(content=openapi)


# Custom docs and redoc
from fastapi.openapi.docs import (
    get_swagger_ui_html,
    get_redoc_html,
)


@app.get("/docs", include_in_schema=False)
async def custom_docs():
    return get_swagger_ui_html(openapi_url="/openapi.json", title="API Gateway Docs")


@app.get("/redoc", include_in_schema=False)
async def custom_redoc():
    return get_redoc_html(openapi_url="/openapi.json", title="API Gateway ReDoc")
