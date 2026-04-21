import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.admin import router as admin_router
from app.config import settings
from app.credentials import CredentialsStore
from app.gateway_sync import sync_with_gateway
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
    # Startup sync — fire-and-forget so lifespan is not blocked if the gateway
    # is down (retries take up to ~150s; admin API must still come up).
    asyncio.create_task(sync_with_gateway(supervisor))
    yield
    if supervisor:
        await supervisor.shutdown()
    logger.info("runner shut down")


app = FastAPI(title="mcp-google-templates-runner", lifespan=lifespan)
app.include_router(admin_router)


@app.get("/admin/health")
async def health():
    return {"status": "ok"}
