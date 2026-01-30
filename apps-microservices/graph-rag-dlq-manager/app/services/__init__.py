"""
RabbitMQ Management API client for DLQ operations.
Uses the RabbitMQ Management HTTP API to list and manage queue messages.
"""

import json
import logging
import httpx
import aio_pika
from typing import List, Optional, Dict, Any
from urllib.parse import quote
from app.core.config import settings
from app.schemas.dlq import DLQMessage, DLQQueue


class RabbitMQManagementClient:
    """Client for interacting with RabbitMQ Management API and AMQP."""

    def __init__(self):
        self.api_url = settings.get_api_url()
        self.auth = (settings.get_api_user(), settings.get_api_password())
        self.vhost = settings.get_vhost()
        self.connection = None
        self.channel = None

    def _get_vhost_encoded(self) -> str:
        """URL encode the vhost for API calls."""
        return quote(self.vhost, safe="")

    async def connect_amqp(self):
        """Establish AMQP connection for publishing."""
        if not self.connection or self.connection.is_closed:
            self.connection = await aio_pika.connect_robust(settings.RABBITMQ_URL)
            self.channel = await self.connection.channel()
            logging.info("✅ Connected to RabbitMQ via AMQP")

    async def close(self):
        """Close AMQP connection."""
        if self.connection and not self.connection.is_closed:
            await self.connection.close()
            logging.info("🔒 Closed RabbitMQ AMQP connection")

    async def list_dlq_queues(self) -> List[DLQQueue]:
        """List all queues that contain 'dlq' or 'manual' in their name."""
        try:
            vhost = self._get_vhost_encoded()
            async with httpx.AsyncClient(auth=self.auth, timeout=30.0) as client:
                response = await client.get(f"{self.api_url}/queues/{vhost}")
                response.raise_for_status()
                queues_data = response.json()

            dlq_queues = []
            for q in queues_data:
                name = q.get("name", "")
                # Filter for DLQ-related queues
                if (
                    "dlq" in name.lower()
                    or "manual" in name.lower()
                    or "retry" in name.lower()
                ):
                    dlq_queues.append(
                        DLQQueue(
                            name=name,
                            message_count=q.get("messages", 0),
                            consumer_count=q.get("consumers", 0),
                            state=q.get("state", "unknown"),
                        )
                    )
            return dlq_queues

        except httpx.HTTPError as e:
            logging.error(f"Failed to list queues: {e}")
            raise

    async def get_messages(
        self,
        queue_name: str,
        count: int = 20,
        ack_mode: str = "ack_requeue_true",
        routing_key_filter: Optional[str] = None,
        exchange_filter: Optional[str] = None,
    ) -> List[DLQMessage]:
        """
        Get messages from a queue using the Management API.

        Args:
            queue_name: Name of the queue to get messages from
            count: Maximum number of messages to retrieve
            ack_mode: How to handle messages:
                - 'ack_requeue_true': Get messages but leave them in the queue
                - 'ack_requeue_false': Get and remove messages from queue
            routing_key_filter: Optional filter by routing key
            exchange_filter: Optional filter by exchange
        """
        try:
            vhost = self._get_vhost_encoded()
            queue_encoded = quote(queue_name, safe="")

            # RabbitMQ Management API payload for getting messages
            payload = {
                "count": count,
                "ackmode": ack_mode,
                "encoding": "auto",
                "truncate": 50000,  # Truncate large messages
            }

            async with httpx.AsyncClient(auth=self.auth, timeout=30.0) as client:
                response = await client.post(
                    f"{self.api_url}/queues/{vhost}/{queue_encoded}/get",
                    json=payload,
                )
                response.raise_for_status()
                messages_data = response.json()

            messages = []
            for idx, msg in enumerate(messages_data):
                properties = msg.get("properties", {})
                headers = properties.get("headers", {})

                # Parse payload
                payload_raw = msg.get("payload", "{}")
                try:
                    if isinstance(payload_raw, str):
                        payload_parsed = json.loads(payload_raw)
                    else:
                        payload_parsed = payload_raw
                except json.JSONDecodeError:
                    payload_parsed = {"raw": payload_raw}

                # Get routing key and exchange from message
                msg_routing_key = msg.get("routing_key", "")
                msg_exchange = msg.get("exchange", "")

                # Apply filters if specified
                if routing_key_filter and routing_key_filter not in msg_routing_key:
                    continue
                if exchange_filter and exchange_filter not in msg_exchange:
                    continue

                # Generate a pseudo message ID (RabbitMQ doesn't have built-in message IDs)
                message_id = (
                    properties.get("message_id")
                    or f"{queue_name}_{idx}_{msg.get('message_count', idx)}"
                )

                messages.append(
                    DLQMessage(
                        message_id=message_id,
                        queue_name=queue_name,
                        exchange=msg_exchange,
                        routing_key=msg_routing_key,
                        payload=payload_parsed,
                        headers=headers,
                        timestamp=properties.get("timestamp"),
                        redelivered=msg.get("redelivered", False),
                    )
                )

            return messages

        except httpx.HTTPError as e:
            logging.error(f"Failed to get messages from {queue_name}: {e}")
            raise

    async def requeue_messages(
        self,
        queue_name: str,
        target_exchange: str,
        target_routing_key: str,
        count: int = 10,
    ) -> Dict[str, Any]:
        """
        Requeue messages from a DLQ queue to another exchange.

        This function:
        1. Gets messages from the source queue (with ack_requeue_false to remove them)
        2. Publishes them to the target exchange with the specified routing key
        """
        try:
            await self.connect_amqp()

            # Get messages from source queue (this removes them)
            messages = await self.get_messages(
                queue_name=queue_name,
                count=count,
                ack_mode="ack_requeue_false",
            )

            if not messages:
                return {
                    "success": True,
                    "message": "No messages found in queue",
                    "processed_count": 0,
                }

            # Declare target exchange
            exchange = await self.channel.declare_exchange(
                target_exchange,
                aio_pika.ExchangeType.TOPIC,
                durable=True,
            )

            processed_count = 0
            errors = []

            for msg in messages:
                try:
                    # Re-publish the message payload
                    message_body = json.dumps(msg.payload).encode("utf-8")
                    amqp_message = aio_pika.Message(
                        body=message_body,
                        delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                    )
                    await exchange.publish(amqp_message, routing_key=target_routing_key)
                    processed_count += 1
                    logging.info(
                        f"📤 Requeued message {msg.message_id} to {target_exchange}/{target_routing_key}"
                    )
                except Exception as e:
                    errors.append(
                        f"Failed to requeue message {msg.message_id}: {str(e)}"
                    )
                    logging.error(f"Failed to requeue message: {e}")

            return {
                "success": len(errors) == 0,
                "message": f"Requeued {processed_count} messages",
                "processed_count": processed_count,
                "errors": errors,
            }

        except Exception as e:
            logging.error(f"Requeue operation failed: {e}")
            return {
                "success": False,
                "message": str(e),
                "processed_count": 0,
                "errors": [str(e)],
            }

    async def delete_messages(
        self,
        queue_name: str,
        count: int = 1,
    ) -> Dict[str, Any]:
        """
        Delete (acknowledge and discard) messages from a queue.

        This uses ack_requeue_false to permanently remove messages.
        """
        try:
            # Get messages with ack_requeue_false to remove them
            messages = await self.get_messages(
                queue_name=queue_name,
                count=count,
                ack_mode="ack_requeue_false",
            )

            return {
                "success": True,
                "message": f"Deleted {len(messages)} messages from {queue_name}",
                "processed_count": len(messages),
                "errors": [],
            }

        except Exception as e:
            logging.error(f"Delete operation failed: {e}")
            return {
                "success": False,
                "message": str(e),
                "processed_count": 0,
                "errors": [str(e)],
            }

    async def purge_queue(self, queue_name: str) -> Dict[str, Any]:
        """Purge all messages from a queue."""
        try:
            vhost = self._get_vhost_encoded()
            queue_encoded = quote(queue_name, safe="")

            async with httpx.AsyncClient(auth=self.auth, timeout=30.0) as client:
                response = await client.delete(
                    f"{self.api_url}/queues/{vhost}/{queue_encoded}/contents"
                )
                response.raise_for_status()

            return {
                "success": True,
                "message": f"Purged all messages from {queue_name}",
                "processed_count": 0,
                "errors": [],
            }

        except httpx.HTTPError as e:
            logging.error(f"Purge operation failed: {e}")
            return {
                "success": False,
                "message": str(e),
                "processed_count": 0,
                "errors": [str(e)],
            }


# Singleton instance
rabbitmq_client = RabbitMQManagementClient()
