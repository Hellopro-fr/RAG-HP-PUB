from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.openapi.utils import get_openapi
from fastapi.responses import Response
from app.core.settings import settings, SERVICE_MAP
import httpx
import websockets

app = FastAPI(
    title="API Gateway",
    docs_url=None,         # disable default docs
    redoc_url=None,
    openapi_url=None
)

# Proxy requests to backend services
@app.api_route("/{service}/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"], include_in_schema=False)
async def proxy(service: str, path: str, request: Request):
    base_url = SERVICE_MAP.get(f"/{service}")
    if not base_url:
        return JSONResponse(status_code=404, content={"detail": "Service not found"})

    url = f"{base_url}/{path}"
    print(url)
    method = request.method
    headers = dict(request.headers)
    headers = {
        "accept": "*/*",
        "user-agent": "Mozilla/5.0 (api-gateway)",
        "referer": base_url,
        "origin": base_url,
    }

    body = await request.body()

    async with httpx.AsyncClient() as client:
        response = await client.request(
            method, url, headers=headers, content=body, timeout=None
        )

    if response.status_code == 403:
        print("403 error body:", response.text)
    # Forward the response content and headers directly
    return Response(
        content=response.content,
        status_code=response.status_code,
        media_type=response.headers.get("content-type")
    )
    
@app.websocket("/{service}/{path:path}")
async def websocket_proxy(service: str, path: str, websocket: WebSocket):
    """
    Proxy pour les connexions WebSocket.
    """
    base_url = SERVICE_MAP.get(f"/{service}")
    if not base_url:
        # FastAPI ne gère pas bien les réponses d'erreur avant accept(),
        # donc nous fermons simplement la connexion.
        await websocket.close(code=1008) # Policy Violation
        return

    # Convertir l'URL http:// en ws://
    ws_url = base_url.replace("http://", "ws://").replace("https://", "wss://")
    target_url = f"{ws_url}/{path}"
    
    # Accepter la connexion du client
    await websocket.accept()

    try:
        # Établir une connexion WebSocket avec le service backend
        async with websockets.connect(target_url, extra_headers=websocket.headers.raw_items()) as backend_ws:
            
            # Tâches pour relayer les messages dans les deux sens
            async def forward_to_backend():
                try:
                    while True:
                        data = await websocket.receive_text()
                        logger.debug(f"Client -> Backend: {data[:100]}") # Log tronqué
                        await backend_ws.send(data)
                except WebSocketDisconnect:
                    logger.info("Le client a fermé la connexion (forward_to_backend).")

            async def forward_to_client():
                try:
                    while True:
                        data = await backend_ws.recv()
                        logger.debug(f"Backend -> Client: {data[:100]}") # Log tronqué
                        await websocket.send_text(data)
                except websockets.exceptions.ConnectionClosed:
                    logger.info("Le backend a fermé la connexion (forward_to_client).")

            # Lancer les deux tâches en parallèle
            client_task = asyncio.create_task(forward_to_backend())
            backend_task = asyncio.create_task(forward_to_client())

            # Attendre que l'une des tâches se termine (ce qui signifie une déconnexion)
            done, pending = await asyncio.wait(
                [client_task, backend_task],
                return_when=asyncio.FIRST_COMPLETED,
            )
            
            # Annuler les tâches restantes pour nettoyer
            for task in pending:
                task.cancel()
            logger.info("Une des connexions a été fermée, nettoyage des tâches en cours.")

    except (WebSocketDisconnect, websockets.exceptions.ConnectionClosed):
        print(f"WebSocket déconnecté pour {service}/{path}")
    except Exception as e:
        print(f"Erreur dans le proxy WebSocket : {e}")
    finally:
        # Assurez-vous que les connexions sont bien fermées
        await websocket.close()


# Combine all OpenAPI schemas
@app.get("/openapi.json", include_in_schema=False)
async def custom_openapi():
    openapi = get_openapi(
        title="API Gateway",
        version="1.0.0",
        description="Combined schema of all microservices",
        routes=app.routes,
    )

    async with httpx.AsyncClient() as client:
        for prefix, url in SERVICE_MAP.items():
            try:
                r = await client.get(f"{url}/openapi.json")
                r.raise_for_status()
                sub_openapi = r.json()

                # Merge paths with prefix
                for path, path_data in sub_openapi.get("paths", {}).items():
                    openapi["paths"][f"{prefix}{path}"] = path_data

                # Merge components (schemas, responses, parameters, etc.)
                if "components" in sub_openapi:
                    if "components" not in openapi:
                        openapi["components"] = {}

                    for comp_type, comp_dict in sub_openapi["components"].items():
                        if comp_type not in openapi["components"]:
                            openapi["components"][comp_type] = {}

                        # Merge each component entry without overwriting existing keys
                        for key, val in comp_dict.items():
                            if key not in openapi["components"][comp_type]:
                                openapi["components"][comp_type][key] = val

            except Exception as e:
                print(f"Failed to fetch schema from {url}: {e}")

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
