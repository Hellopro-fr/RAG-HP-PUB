from fastapi import APIRouter, Depends, Header, HTTPException, Response

from app.core.settings import get_settings
from app.schemas import ClientSummary, CreateClientRequest, CreateClientResponse
from app.services.client_service import (
    ClientNotFound,
    create_client,
    delete_client,
    list_clients,
)

router = APIRouter(prefix="/admin/clients", tags=["admin"])


async def _require_admin_key(
    x_admin_key: str | None = Header(default=None, alias="X-Admin-Key"),
):
    if x_admin_key != get_settings().GATEWAY_ADMIN_KEY:
        raise HTTPException(status_code=403, detail={"error": "forbidden"})


@router.post(
    "",
    status_code=201,
    response_model=CreateClientResponse,
    dependencies=[Depends(_require_admin_key)],
)
async def admin_create(req: CreateClientRequest):
    try:
        secret = await create_client(
            client_id=req.client_id,
            name=req.name,
            redirect_uris=[str(u) for u in req.redirect_uris],
            post_logout_redirect_uris=[str(u) for u in req.post_logout_redirect_uris],
            skip_consent=req.skip_consent,
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail={"error": str(e)})
    return CreateClientResponse(
        client_id=req.client_id, client_secret=secret, name=req.name
    )


@router.get(
    "",
    response_model=list[ClientSummary],
    dependencies=[Depends(_require_admin_key)],
)
async def admin_list():
    clients = await list_clients()
    return [
        ClientSummary(
            client_id=c.client_id,
            name=c.name,
            redirect_uris=c.redirect_uris,
            skip_consent=c.skip_consent,
            is_active=c.is_active,
            created_at=c.created_at,
        )
        for c in clients
    ]


@router.delete(
    "/{client_id}",
    status_code=204,
    dependencies=[Depends(_require_admin_key)],
)
async def admin_delete(client_id: str):
    try:
        await delete_client(client_id)
    except ClientNotFound:
        raise HTTPException(status_code=404, detail={"error": "not_found"})
    return Response(status_code=204)
