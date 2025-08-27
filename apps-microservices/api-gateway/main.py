from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.openapi.utils import get_openapi
from fastapi.responses import Response
from app.core.settings import settings, SERVICE_MAP
import httpx

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
            method, url, headers=headers, content=body
        )

    if response.status_code == 403:
        print("403 error body:", response.text)
    # Forward the response content and headers directly
    return Response(
        content=response.content,
        status_code=response.status_code,
        media_type=response.headers.get("content-type")
    )


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
