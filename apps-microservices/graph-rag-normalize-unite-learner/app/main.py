"""
Entrypoint du learner — déclenchement MANUEL par API REST.

POST /run {limit?}  -> draine `limit` (défaut 100) messages du manual DLQ, apprend
les unités (LLM + Gate 1 fidèle), écrit INACTIF, et retourne un rapport.
Un seul run à la fois (verrou) ; 1 seul réplica recommandé en déploiement.
"""
import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional

import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel

from common_utils.metrics.prometheus import start_metrics_server_in_thread

from app.config import settings
from app.core.batch import BatchRunner
from app.core.learner import Learner, ProcessingError

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", force=True
)
logger = logging.getLogger(__name__)


class RunRequest(BaseModel):
    limit: Optional[int] = None  # défaut settings.DEFAULT_LIMIT (100)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.learner = Learner()
    app.state.run_lock = asyncio.Lock()
    yield
    await app.state.learner.close()


def create_app() -> FastAPI:
    app = FastAPI(title="graph-rag-normalize-unite-learner", lifespan=lifespan)

    @app.get("/health")
    async def health() -> Dict[str, str]:
        return {"status": "ok"}

    @app.post("/run")
    async def run(req: RunRequest) -> Dict[str, Any]:
        # Un seul run à la fois (évite le double-drainage du DLQ)
        if app.state.run_lock.locked():
            return {"started": False, "message": "un run est déjà en cours"}
        async with app.state.run_lock:
            runner = BatchRunner(app.state.learner)
            try:
                report = await runner.run(req.limit)
            except ProcessingError as exc:
                # Pré-requis du run non satisfaits (#8 : référentiel vide/incohérent, BO injoignable)
                logger.warning("Run non démarré: %s", exc)
                return {"started": False, "error": str(exc)}
            logger.info("Run terminé: %s", report)
            return {"started": True, "report": report}

    return app


app = create_app()


def main():
    start_metrics_server_in_thread(port=settings.PROMETHEUS_PORT)
    uvicorn.run(app, host="0.0.0.0", port=settings.REST_PORT)


if __name__ == "__main__":
    main()
