import logging
import time
from infrastructure.grpc_server import serve
from application.normalization_use_case import NormalizationUseCase
from common_utils.metrics.prometheus import start_metrics_server_in_thread
from app.config import settings

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


def main():
    start_metrics_server_in_thread(port=settings.PROMETHEUS_PORT)

    use_case = NormalizationUseCase()

    logging.info("Starting Graph RAG Normalize Unite Service...")
    serve(use_case)


if __name__ == "__main__":
    main()
