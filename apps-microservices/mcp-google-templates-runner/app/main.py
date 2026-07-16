import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.admin import router as admin_router
from app.config import settings
from app.credentials import CredentialsStore
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
    pool = PortPool(
        settings.runner_instance_port_start, settings.runner_instance_port_end
    )
    creds = CredentialsStore(settings.secrets_dir)
    supervisor = Supervisor(pool=pool, credentials=creds)
    logger.info(
        "runner started; gateway=%s ports=%d-%d",
        settings.mcp_gateway_url,
        settings.runner_instance_port_start,
        settings.runner_instance_port_end,
    )
    # Background reconcile loop — fire-and-forget so lifespan is not blocked if
    # the gateway is down. The loop runs immediately at boot and keeps retrying
    # on a short interval until the gateway is reachable, then settles to a long
    # interval. This is what prevents a boot-time gateway-DNS race from leaving
    # the runner with empty state forever, and self-heals port drift.
    # Held on app.state so shutdown can cancel it cleanly — otherwise Python
    # prints "Task was destroyed but it is pending!" if shutdown lands mid-retry.
    app.state.sync_task = asyncio.create_task(reconcile_loop(supervisor))
    yield
    app.state.sync_task.cancel()
    await asyncio.gather(app.state.sync_task, return_exceptions=True)
    if supervisor:
        await supervisor.shutdown()
    logger.info("runner shut down")


app = FastAPI(title="mcp-google-templates-runner", lifespan=lifespan)
app.include_router(admin_router)


@app.get("/admin/health")
async def health():
    return {"status": "ok"}
