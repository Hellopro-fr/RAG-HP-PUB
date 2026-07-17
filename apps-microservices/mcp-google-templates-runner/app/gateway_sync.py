from __future__ import annotations

import asyncio
import logging
import random

import httpx

from app.config import settings
from app.supervisor import SpawnSpec, Supervisor

logger = logging.getLogger("runner.sync")


async def sync_with_gateway(sup: Supervisor, retries: int = 5) -> None:
    """On boot, fetch desired instances from the gateway and spawn them.

    Non-blocking: called via `asyncio.create_task` from the FastAPI lifespan so
    the runner accepts admin API calls even if the gateway is unreachable at
    boot. Retries with exponential backoff + jitter to avoid thundering-herd
    when many runners start at once.
    """
    url = settings.mcp_gateway_url.rstrip("/") + "/api/v1/internal/runner/sync"
    headers = {"X-Admin-Token": settings.mcp_gateway_admin_token}

    for attempt in range(retries):
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(url, headers=headers, json={})
                resp.raise_for_status()
                body = resp.json()
            desired = body.get("desired_instances", [])
            logger.info("startup sync: %d desired instances", len(desired))

            sem = asyncio.Semaphore(5)

            async def _spawn(spec_dict: dict) -> None:
                async with sem:
                    try:
                        await sup.spawn(SpawnSpec(**spec_dict))
                    except Exception:
                        logger.exception(
                            "failed to spawn %s", spec_dict.get("instance_id")
                        )

            await asyncio.gather(
                *[_spawn(d) for d in desired], return_exceptions=True
            )
            return
        except Exception as e:
            logger.warning("startup sync attempt %d failed: %s", attempt + 1, e)
            if attempt < retries - 1:
                await asyncio.sleep(min(2 ** attempt, 30) + random.uniform(0, 1))

    logger.error(
        "startup sync: giving up after %d attempts — running with empty state",
        retries,
    )


async def reconcile_once(sup: Supervisor) -> bool:
    """Pull the desired instance set from the gateway and converge to it.

    Idempotent: spawns only instances that are missing or whose credentials
    hash changed, and kills instances the gateway no longer wants. Running,
    unchanged instances are left untouched — so this is safe to call on a
    repeating loop without restarting healthy subprocesses.

    Returns True when the gateway was reachable and reconciliation ran, False
    when the gateway could not be contacted (caller retries on the short
    interval). A single unreachable gateway never mutates local state.
    """
    url = settings.mcp_gateway_url.rstrip("/") + "/api/v1/internal/runner/sync"
    headers = {"X-Admin-Token": settings.mcp_gateway_admin_token}

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, headers=headers, json={})
            resp.raise_for_status()
            body = resp.json()
    except Exception as e:
        logger.warning("gateway reconcile failed: %s", e)
        return False

    desired = {d["instance_id"]: d for d in body.get("desired_instances", [])}
    local = {inst.instance_id: inst for inst in sup.list()}

    to_kill = [iid for iid in local if iid not in desired]
    to_spawn = [
        d
        for iid, d in desired.items()
        if iid not in local or local[iid].credentials_hash != d.get("credentials_hash")
    ]

    for iid in to_kill:
        try:
            await sup.kill(iid)
        except Exception:
            logger.exception("reconcile: kill failed for %s", iid)

    sem = asyncio.Semaphore(5)

    async def _spawn(spec_dict: dict) -> None:
        async with sem:
            try:
                await sup.spawn(SpawnSpec(**spec_dict))
            except Exception:
                logger.exception(
                    "reconcile: spawn failed for %s", spec_dict.get("instance_id")
                )

    await asyncio.gather(*[_spawn(d) for d in to_spawn], return_exceptions=True)
    logger.info(
        "reconcile: %d desired, %d spawned, %d killed",
        len(desired),
        len(to_spawn),
        len(to_kill),
    )
    return True


async def reconcile_loop(
    sup: Supervisor,
    ok_interval: float | None = None,
    fail_interval: float | None = None,
) -> None:
    """Run reconcile_once forever, starting immediately.

    The first iteration runs at boot, so a gateway that is briefly
    unresolvable at startup no longer orphans every instance permanently — the
    next tick repopulates them. After a successful reconcile the loop waits the
    long interval; after a failure it retries on the short interval until the
    gateway comes back. Also corrects port drift (instances spawned on a
    different port after a restart re-converge to the gateway's desired set).
    """
    ok = ok_interval if ok_interval is not None else settings.runner_reconcile_interval_sec
    fail = fail_interval if fail_interval is not None else settings.runner_reconcile_retry_sec
    while True:
        try:
            success = await reconcile_once(sup)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("reconcile loop iteration crashed")
            success = False
        await asyncio.sleep(ok if success else fail)
