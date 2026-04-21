import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import settings

logger = logging.getLogger("runner")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        "runner starting; gateway=%s port_pool=%d-%d",
        settings.mcp_gateway_url,
        settings.runner_instance_port_start,
        settings.runner_instance_port_end,
    )
    # Supervisor setup + gateway startup sync are wired in Tasks 18 and 19.
    yield
    logger.info("runner shutting down")
    # Supervisor.shutdown is wired in Task 17.


app = FastAPI(title="mcp-google-templates-runner", lifespan=lifespan)


@app.get("/admin/health")
async def health():
    return {"status": "ok"}
