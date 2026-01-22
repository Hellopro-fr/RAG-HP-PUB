import asyncio
import logging
from app.messaging.consumer import RabbitMQConsumer
from common_utils.metrics.prometheus import start_metrics_server_in_thread
from app.config import settings

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


async def main():
    start_metrics_server_in_thread(port=settings.PROMETHEUS_PORT)
    consumer = RabbitMQConsumer()
    try:
        await consumer.start()
    except KeyboardInterrupt:
        pass
    finally:
        consumer.close()


if __name__ == "__main__":
    asyncio.run(main())
