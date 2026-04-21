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
            await asyncio.sleep(min(2 ** attempt, 30) + random.uniform(0, 1))

    logger.error(
        "startup sync: giving up after %d attempts — running with empty state",
        retries,
    )
