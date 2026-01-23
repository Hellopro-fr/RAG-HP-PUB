import aio_pika
from aio_pika.abc import AbstractIncomingMessage


class DLQPropertiesAsync:
    @staticmethod
    def create_dlq_headers(
        error: Exception,
        service_name: str,
        retry_count: int,
        message: AbstractIncomingMessage,
    ) -> dict:
        """
        Creates a dictionary of headers for a DLQ message based on an aio_pika message.
        """
        # Extract original routing details safely
        original_exchange = message.exchange or "N/A"
        original_routing_key = message.routing_key or "N/A"

        headers = {
            "x-error-reason": str(error),
            "x-service-name": service_name,
            "x-retry-count": retry_count,
            "x-original-exchange": str(original_exchange),
            "x-original-routing-key": str(original_routing_key),
        }
        return headers

    @staticmethod
    def create_dlq_message(
        error: Exception,
        service_name: str,
        retry_count: int,
        message: AbstractIncomingMessage,
    ) -> aio_pika.Message:
        """
        Creates a persistent aio_pika.Message ready for the Dead Letter Queue.
        """
        headers = DLQPropertiesAsync.create_dlq_headers(
            error, service_name, retry_count, message
        )

        return aio_pika.Message(
            body=message.body,
            headers=headers,
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        )
