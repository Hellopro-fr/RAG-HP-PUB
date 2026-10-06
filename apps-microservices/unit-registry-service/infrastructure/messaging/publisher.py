"""RabbitMQ publisher for the normalization.units fanout (publisher confirms on)."""
from __future__ import annotations

import logging
from typing import Protocol

import pika

logger = logging.getLogger(__name__)


class Publisher(Protocol):
    def publish(self, body: bytes) -> None: ...  # raises on nack or connection loss
    def heartbeat(self) -> None: ...
    def reset(self) -> None: ...


class PikaPublisher:
    def __init__(self, url: str, exchange: str):
        self._url = url
        self._exchange = exchange
        self._connection: pika.BlockingConnection | None = None
        self._channel = None

    def _ensure_channel(self):
        if self._channel is None or self._channel.is_closed:
            self._connection = pika.BlockingConnection(pika.URLParameters(self._url))
            self._channel = self._connection.channel()
            self._channel.exchange_declare(exchange=self._exchange, exchange_type="fanout", durable=True)
            self._channel.confirm_delivery()
        return self._channel

    def publish(self, body: bytes) -> None:
        self._ensure_channel().basic_publish(
            exchange=self._exchange,
            routing_key="",
            body=body,
            properties=pika.BasicProperties(content_type="application/json",
                                            delivery_mode=pika.DeliveryMode.Persistent),
        )

    def heartbeat(self) -> None:
        if self._connection is not None and self._connection.is_open:
            self._connection.process_data_events(time_limit=0)

    def reset(self) -> None:
        try:
            if self._connection is not None and self._connection.is_open:
                self._connection.close()
        except Exception:  # closing a broken connection may raise; nothing to recover
            logger.debug("ignoring error while closing RabbitMQ connection", exc_info=True)
        self._connection = None
        self._channel = None
