import asyncio
import logging
import uvloop

from infrastructure.grpc_server import serve
from application.spacy_use_case import SpacyUseCase
from common_utils.metrics.prometheus import start_metrics_server_in_thread
from app.config import settings

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


async def main():
    start_metrics_server_in_thread(port=settings.PROMETHEUS_PORT)
    use_case = SpacyUseCase()
    await serve(use_case)


if __name__ == "__main__":
    uvloop.install()
    asyncio.run(main())
