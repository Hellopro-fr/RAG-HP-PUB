import logging
import threading

from app.config import settings
from common_utils.metrics.prometheus import start_metrics_server_in_thread
from application.normalization_use_case import NormalizationUseCase
from infrastructure.grpc_server import serve
from infrastructure.registry_client import RegistryClient
from infrastructure.unit_events_consumer import UnitEventsConsumer
from infrastructure.unit_normalization_service import unit_state

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


def main():
    start_metrics_server_in_thread(port=settings.PROMETHEUS_PORT)

    if settings.RABBITMQ_URL:
        consumer = UnitEventsConsumer(
            settings.RABBITMQ_URL,
            settings.UNITS_EXCHANGE,
            unit_state,
            RegistryClient(settings.UNIT_REGISTRY_GRPC_ADDR),
        )
        threading.Thread(target=consumer.run_forever, args=(threading.Event(),),
                         daemon=True, name="unit-events").start()
    else:
        logging.warning("RABBITMQ_URL is not set: serving the frozen fallback unit tables, live updates disabled")

    use_case = NormalizationUseCase()

    logging.info("Starting Graph RAG Normalize Unite Service...")
    serve(use_case)


if __name__ == "__main__":
    main()
