import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.admin import router as admin_router
from app.config import settings
from app.gateway_sync import reconcile_loop
from app.port_pool import PortPool
from app.supervisor import Supervisor

logger = logging.getLogger("runner")
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)

supervisor: Supervisor | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global supervisor
    pool = PortPool(settings.runner_instance_port_start, settings.runner_instance_port_end)
    supervisor = Supervisor(pool=pool)
    logger.info(
        "runner started; gateway=%s ports=%d-%d",
        settings.mcp_gateway_url,
        settings.runner_instance_port_start,
        settings.runner_instance_port_end,
    )
    # Fire-and-forget reconcile loop (boot + periodic), same as the Google
    # runner: a gateway unreachable at boot is retried on the short interval.
    app.state.sync_task = asyncio.create_task(reconcile_loop(supervisor))
    yield
    app.state.sync_task.cancel()
    await asyncio.gather(app.state.sync_task, return_exceptions=True)
    if supervisor:
        await supervisor.shutdown()
    logger.info("runner shut down")


app = FastAPI(title="mcp-template-neo4j-service", lifespan=lifespan)
app.include_router(admin_router)


@app.get("/admin/health")
async def health():
    return {"status": "ok"}
