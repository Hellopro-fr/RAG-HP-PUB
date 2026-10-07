"""Consumes the normalization.units fanout and keeps UnitStateHolder in sync (spec §5)."""
from __future__ import annotations

import json
import logging
import threading
from typing import Callable

import pika

from unit_registry.bundle import BundleBuildError

from .unit_metrics import EVENTS, RESYNCS
from .unit_state import UnitStateHolder

logger = logging.getLogger(__name__)


class UnitEventsConsumer:
    def __init__(self, rabbitmq_url: str, exchange: str, holder: UnitStateHolder, client, *,
                 connect: Callable[[], object] | None = None, max_backoff: float = 60.0):
        self._exchange = exchange
        self._holder = holder
        self._client = client
        self._connect = connect or (lambda: pika.BlockingConnection(pika.URLParameters(rabbitmq_url)))
        self._max_backoff = max_backoff

    def resync(self) -> None:
        units, version = self._client.list_active()
        self._holder.load_full(units, version)
        RESYNCS.inc()
        logger.info("loaded %d active units at registry_version %d", len(units), version)

    def handle_body(self, body: bytes) -> str:
        try:
            event = json.loads(body)
        except ValueError:
            logger.error("dropping a non-JSON unit event")
            EVENTS.labels("invalid").inc()
            return "invalid"
        try:
            result = self._holder.apply_event(event)
        except BundleBuildError:
            logger.exception("unit event breaks the registry; keeping the last good tables")
            EVENTS.labels("failed").inc()
            return "failed"
        except (KeyError, TypeError, ValueError):
            logger.exception("dropping a malformed unit event")
            EVENTS.labels("invalid").inc()
            return "invalid"
        EVENTS.labels(result).inc()
        if result == "gap":
            self.resync()
        return result

    def _try_resync(self) -> None:
        try:
            self.resync()
        except Exception:
            logger.warning("initial unit load failed; serving %s tables", self._holder.source, exc_info=True)

    def run_forever(self, stop: threading.Event) -> None:
        self._try_resync()  # best effort even if RabbitMQ is down (Review Focus 3)
        backoff = 1.0
        while not stop.is_set():
            connection = None
            try:
                connection = self._connect()
                channel = connection.channel()
                channel.exchange_declare(exchange=self._exchange, exchange_type="fanout", durable=True)
                queue = channel.queue_declare(queue="", exclusive=True, auto_delete=True).method.queue
                channel.queue_bind(queue=queue, exchange=self._exchange)
                self.resync()  # after binding: nothing published from now on can be missed
                backoff = 1.0
                for _method, _properties, body in channel.consume(queue, auto_ack=True, inactivity_timeout=1.0):
                    if stop.is_set():
                        break
                    if body is not None:
                        self.handle_body(body)
            except Exception:
                logger.exception("unit events consumer failed; reconnecting in %.0fs", backoff)
                stop.wait(backoff)
                backoff = min(backoff * 2, self._max_backoff)
            finally:
                if connection is not None and getattr(connection, "is_open", False):
                    try:
                        connection.close()
                    except Exception:
                        logger.debug("ignoring error while closing RabbitMQ connection", exc_info=True)
