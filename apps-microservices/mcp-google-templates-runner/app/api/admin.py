from __future__ import annotations

import asyncio
import time

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth import require_admin_token
from app.models import (
    InstanceListResponse,
    InstanceStatus,
    ReconcileRequest,
    SpawnRequest,
    SpawnResponse,
)
from app.supervisor import Supervisor, SpawnSpec

router = APIRouter(prefix="/admin", dependencies=[Depends(require_admin_token)])


def get_supervisor() -> Supervisor:
    # set by main.py at startup
    from app import main

    if main.supervisor is None:
        raise HTTPException(status_code=503, detail="supervisor not ready")
    return main.supervisor


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
    spec = SpawnSpec(**req.model_dump())
    try:
        inst = await sup.spawn(spec)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"spawn failed: {e}")
    return SpawnResponse(port=inst.port, pid=inst.pid)


@router.delete("/instances/{instance_id}", status_code=status.HTTP_204_NO_CONTENT)
async def kill_instance(instance_id: str, sup: Supervisor = Depends(get_supervisor)):
    await sup.kill(instance_id)
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
    desired = {r.instance_id: r for r in req.desired_instances}
    local = {inst.instance_id: inst for inst in sup.list()}

    # Kill extras
    for iid in list(local.keys()):
        if iid not in desired:
            await sup.kill(iid)

    # Spawn missing + restart hash mismatches (bounded concurrency = 5)
    sem = asyncio.Semaphore(5)

    async def _spawn_one(r: SpawnRequest):
        async with sem:
            await sup.spawn(SpawnSpec(**r.model_dump()))

    to_spawn = []
    for iid, r in desired.items():
        if iid not in local:
            to_spawn.append(r)
        elif local[iid].credentials_hash != r.credentials_hash:
            to_spawn.append(r)

    await asyncio.gather(*[_spawn_one(r) for r in to_spawn])
    return {"spawned": len(to_spawn)}
