from __future__ import annotations

import asyncio
import logging
import time

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth import require_admin_token
from app.config import settings
from app.models import (
    InstanceListResponse,
    InstanceStatus,
    ReconcileRequest,
    SpawnRequest,
    SpawnResponse,
)
from app.neo4j_env import InvalidCredentials, check_stdio_args, parse_credentials
from app.precheck import PrecheckError, verify_connection
from app.supervisor import SpawnSpec, Supervisor

logger = logging.getLogger("runner.admin")

router = APIRouter(prefix="/admin", dependencies=[Depends(require_admin_token)])


def get_supervisor() -> Supervisor:
    # set by main.py at startup
    from app import main

    if main.supervisor is None:
        raise HTTPException(status_code=503, detail="supervisor not ready")
    return main.supervisor


def _unprocessable(code: str, message: str) -> HTTPException:
    # The gateway reads detail.code / detail.message (runnerclient.StatusError.Detail).
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={"code": code, "message": message},
    )


@router.get("/instances", response_model=InstanceListResponse)
async def list_instances(sup: Supervisor = Depends(get_supervisor)):
    items = []
    for inst in sup.list():
        items.append(
            InstanceStatus(
                id=inst.instance_id,
                port=inst.port,
                pid=inst.pid,
                status=inst.status,
                uptime_s=int(time.monotonic() - inst.started_at) if inst.status == "running" else 0,
                last_error=inst.last_error or None,
                stderr_tail="\n".join(list(inst.stderr_ring)) or None,
            )
        )
    return InstanceListResponse(instances=items)


@router.post("/instances", response_model=SpawnResponse)
async def spawn_instance(req: SpawnRequest, sup: Supervisor = Depends(get_supervisor)):
    # Admin-requested spawn (create / rotate): validate and pre-check BEFORE the
    # supervisor kills any running process for this id, so a rejected rotate
    # leaves the previous instance serving.
    try:
        check_stdio_args(req.stdio_args)
        creds = parse_credentials(req.credentials_json)
    except InvalidCredentials as e:
        raise _unprocessable("neo4j_invalid_credentials", str(e))
    try:
        await verify_connection(creds, settings.neo4j_precheck_timeout_sec)
    except PrecheckError as e:
        logger.warning("pre-check failed for instance %s: %s", req.instance_id, e.code)
        raise _unprocessable(e.code, e.message)
    spec = SpawnSpec(**req.model_dump())
    try:
        inst = await sup.spawn(spec)
    except Exception:
        logger.exception("spawn failed for instance %s", req.instance_id)
        raise HTTPException(status_code=500, detail="spawn failed — see server logs")
    return SpawnResponse(port=inst.port, pid=inst.pid)


@router.delete("/instances/{instance_id}", status_code=status.HTTP_204_NO_CONTENT)
async def kill_instance(instance_id: str, sup: Supervisor = Depends(get_supervisor)):
    try:
        await sup.kill(instance_id)
    except Exception:
        logger.exception("kill failed for instance %s", instance_id)
        raise HTTPException(status_code=500, detail="kill failed — see server logs")
    return None


@router.post("/instances/{instance_id}/restart", status_code=status.HTTP_202_ACCEPTED)
async def restart_instance(instance_id: str, sup: Supervisor = Depends(get_supervisor)):
    try:
        await sup.restart(instance_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="instance not found")
    return {"status": "restarting"}


@router.post("/reconcile", status_code=status.HTTP_202_ACCEPTED)
async def reconcile(req: ReconcileRequest, sup: Supervisor = Depends(get_supervisor)):
    # No pre-check here: reconcile restores desired state, and must not drop
    # instances because Neo4j is briefly unavailable.
    desired = {r.instance_id: r for r in req.desired_instances}
    local = {inst.instance_id: inst for inst in sup.list()}

    for iid in list(local.keys()):
        if iid not in desired:
            await sup.kill(iid)

    sem = asyncio.Semaphore(5)

    async def _spawn_one(r: SpawnRequest):
        async with sem:
            try:
                await sup.spawn(SpawnSpec(**r.model_dump()))
            except Exception:
                logger.exception("reconcile: spawn failed for %s", r.instance_id)

    to_spawn = []
    for iid, r in desired.items():
        if iid not in local:
            to_spawn.append(r)
        elif local[iid].credentials_hash != r.credentials_hash:
            to_spawn.append(r)

    await asyncio.gather(*[_spawn_one(r) for r in to_spawn], return_exceptions=True)
    return {"spawned": len(to_spawn)}
