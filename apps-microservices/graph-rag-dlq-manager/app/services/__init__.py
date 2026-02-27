"""
RabbitMQ AMQP client for DLQ operations.
Uses pure AMQP via aio_pika to list and manage queue messages.
"""

import json
import logging
import aio_pika
from aio_pika.abc import AbstractIncomingMessage
from typing import List, Optional, Dict, Any
from app.core.config import settings
from app.schemas.dlq import DLQMessage, DLQQueue


class RabbitMQAMQPClient:
    """Client for interacting with RabbitMQ via pure AMQP."""

    def __init__(self):
        self.connection = None
        self.channel = None

    async def connect(self):
        """Establish AMQP connection."""
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
        """
        List all configured DLQ queues with their message counts.
        Uses passive queue declaration to get queue info.
        """
        await self.connect()
        dlq_queues = []

        for queue_name in settings.get_dlq_queue_list():
            try:
                # Passive declare to get queue info without creating it
                queue = await self.channel.declare_queue(
                    queue_name,
                    passive=True,
                )
                dlq_queues.append(
                    DLQQueue(
                        name=queue_name,
                        message_count=queue.declaration_result.message_count,
                        consumer_count=queue.declaration_result.consumer_count,
                        state="running",
                    )
                )
            except aio_pika.exceptions.ChannelNotFoundEntity:
                # Queue doesn't exist
                logging.warning(f"Queue {queue_name} does not exist")
                dlq_queues.append(
                    DLQQueue(
                        name=queue_name,
                        message_count=0,
                        consumer_count=0,
                        state="not_found",
                    )
                )
            except Exception as e:
                logging.error(f"Failed to get info for queue {queue_name}: {e}")
                # Reconnect channel if it closed due to error
                self.channel = await self.connection.channel()
                dlq_queues.append(
                    DLQQueue(
                        name=queue_name,
                        message_count=0,
                        consumer_count=0,
                        state="error",
                    )
                )

        return dlq_queues

    async def get_messages(
        self,
        queue_name: str,
        count: int = 20,
        ack_mode: str = "ack_requeue_true",
        routing_key_filter: Optional[str] = None,
        exchange_filter: Optional[str] = None,
    ) -> List[DLQMessage]:
        """
        Get messages from a queue using AMQP.

        Args:
            queue_name: Name of the queue to get messages from
            count: Maximum number of messages to retrieve
            ack_mode: How to handle messages:
                - 'ack_requeue_true': Get messages but leave them in the queue (peek)
                - 'ack_requeue_false': Get and remove messages from queue
            routing_key_filter: Optional filter by routing key
            exchange_filter: Optional filter by exchange
        """
        await self.connect()

        try:
            # Declare queue passively to ensure it exists
            queue = await self.channel.declare_queue(queue_name, passive=True)
        except aio_pika.exceptions.ChannelNotFoundEntity:
            logging.error(f"Queue {queue_name} does not exist")
            # Reconnect channel
            self.channel = await self.connection.channel()
            return []
        except Exception as e:
            logging.error(f"Failed to access queue {queue_name}: {e}")
            self.channel = await self.connection.channel()
            return []

        messages = []
        fetched_messages: List[AbstractIncomingMessage] = []

        # Fetch messages
        for idx in range(count):
            try:
                message = await queue.get(no_ack=False, timeout=1.0)
                if message is None:
                    break
                fetched_messages.append(message)
            except aio_pika.exceptions.QueueEmpty:
                break
            except Exception as e:
                logging.error(f"Error fetching message: {e}")
                break

        # Process fetched messages
        for idx, msg in enumerate(fetched_messages):
            try:
                # Parse payload
                payload_raw = msg.body.decode("utf-8")
                try:
                    payload_parsed = json.loads(payload_raw)
                except json.JSONDecodeError:
                    payload_parsed = {"raw": payload_raw}

                # Get routing key and exchange from message
                msg_routing_key = msg.routing_key or ""
                msg_exchange = msg.exchange or ""

                # Apply filters if specified
                if routing_key_filter and routing_key_filter not in msg_routing_key:
                    # Requeue filtered messages
                    if ack_mode == "ack_requeue_true":
                        await msg.nack(requeue=True)
                    else:
                        await msg.ack()
                    continue
                if exchange_filter and exchange_filter not in msg_exchange:
                    if ack_mode == "ack_requeue_true":
                        await msg.nack(requeue=True)
                    else:
                        await msg.ack()
                    continue

                # Generate message ID
                message_id = msg.message_id or f"{queue_name}_{idx}_{msg.delivery_tag}"

                # Extract headers
                headers = dict(msg.headers) if msg.headers else {}

                messages.append(
                    DLQMessage(
                        message_id=str(message_id),
                        queue_name=queue_name,
                        exchange=msg_exchange,
                        routing_key=msg_routing_key,
                        payload=payload_parsed,
                        headers=headers,
                        timestamp=str(msg.timestamp) if msg.timestamp else None,
                        redelivered=msg.redelivered,
                    )
                )

                # Handle ack mode
                if ack_mode == "ack_requeue_true":
                    # Peek mode - requeue the message
                    await msg.nack(requeue=True)
                else:
                    # Remove from queue
                    await msg.ack()

            except Exception as e:
                logging.error(f"Error processing message: {e}")
                # Requeue on error
                await msg.nack(requeue=True)

        return messages

    async def requeue_messages(
        self,
        queue_name: str,
        target_exchange: str,
        target_routing_key: str,
        count: int = 10,
        use_original_headers: bool = False,
    ) -> Dict[str, Any]:
        """
        Requeue messages from a DLQ queue to another exchange.

        This function:
        1. Gets messages from the source queue (with ack to remove them)
        2. For each message, checks for x-original-exchange / x-original-routing-key headers
           (set by processor services when publishing to DLQ).
           If found and use_original_headers=True, routes back to the original exchange.
        3. Falls back to the caller-provided target_exchange / target_routing_key.
        """
        try:
            await self.connect()

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

            # Cache of declared exchanges to avoid re-declaring on each message
            declared_exchanges: Dict[str, aio_pika.abc.AbstractExchange] = {}

            async def get_or_declare_exchange(exchange_name: str):
                if exchange_name not in declared_exchanges:
                    declared_exchanges[exchange_name] = (
                        await self.channel.declare_exchange(
                            exchange_name,
                            aio_pika.ExchangeType.TOPIC,
                            durable=True,
                        )
                    )
                return declared_exchanges[exchange_name]

            processed_count = 0
            errors = []

            for msg in messages:
                try:
                    # Determine routing target from original headers if requested
                    headers = msg.headers or {}
                    orig_exchange = headers.get("x-original-exchange")
                    orig_routing_key = headers.get("x-original-routing-key")

                    if use_original_headers and orig_exchange and orig_routing_key:
                        route_exchange = orig_exchange
                        route_routing_key = orig_routing_key
                        logging.info(
                            f"📍 Using original headers: exchange={orig_exchange}, routing_key={orig_routing_key}"
                        )
                    else:
                        route_exchange = target_exchange
                        route_routing_key = target_routing_key

                    # Get or declare the target exchange
                    exchange = await get_or_declare_exchange(route_exchange)

                    # Re-publish the message payload
                    message_body = json.dumps(msg.payload).encode("utf-8")
                    amqp_message = aio_pika.Message(
                        body=message_body,
                        delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                    )
                    await exchange.publish(amqp_message, routing_key=route_routing_key)
                    processed_count += 1
                    logging.info(
                        f"📤 Requeued message {msg.message_id} to {route_exchange}/{route_routing_key}"
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
            await self.connect()

            # Declare queue passively
            queue = await self.channel.declare_queue(queue_name, passive=True)

            # Purge the queue
            purged_count = await queue.purge()

            return {
                "success": True,
                "message": f"Purged {purged_count} messages from {queue_name}",
                "processed_count": purged_count,
                "errors": [],
            }

        except aio_pika.exceptions.ChannelNotFoundEntity:
            self.channel = await self.connection.channel()
            return {
                "success": False,
                "message": f"Queue {queue_name} does not exist",
                "processed_count": 0,
                "errors": [f"Queue {queue_name} not found"],
            }
        except Exception as e:
            logging.error(f"Purge operation failed: {e}")
            return {
                "success": False,
                "message": str(e),
                "processed_count": 0,
                "errors": [str(e)],
            }


# Singleton instance
rabbitmq_client = RabbitMQAMQPClient()
