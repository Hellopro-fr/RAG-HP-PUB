from typing import Optional

from fastapi import APIRouter, FastAPI


def register_api_info(
    app: FastAPI,
    *,
    service: str,
    version: str = "0.0.0",
    ws_endpoints: Optional[list[dict]] = None,
    grpc_address: Optional[str] = None,
    grpc_reflection: bool = False,
    openapi_url: str = "/openapi.json",
) -> None:
    """Register GET /api-info on the given FastAPI app with the catalog convention.

    The endpoint is consumed by api-catalog-service to discover WebSocket
    endpoints and gRPC reflection addresses that aren't exposed via openapi.json.
    """
    router = APIRouter()

    @router.get("/api-info")
    def api_info() -> dict:
        payload: dict = {
            "service": service,
            "version": version,
            "rest": {"openapi_url": openapi_url},
        }
        if ws_endpoints:
            payload["ws"] = {"endpoints": ws_endpoints}
        if grpc_address:
            payload["grpc"] = {"address": grpc_address, "reflection": grpc_reflection}
        return payload

    app.include_router(router)
