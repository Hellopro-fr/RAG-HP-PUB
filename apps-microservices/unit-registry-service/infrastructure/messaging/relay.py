"""Outbox relay: publish unit_events rows in registry_version order, mark each after the broker acks.

A crash between publish and mark re-sends that event; replicas drop it as a duplicate
by registry_version, so delivery is at-least-once and never lossy (spec §5).
"""
from __future__ import annotations

import json
import logging
import threading
from datetime import datetime
from typing import Callable

from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from application.clock import utcnow
from infrastructure.db.models import UnitEventRow

from .publisher import Publisher

logger = logging.getLogger(__name__)


class OutboxRelay:
    def __init__(self, session_factory: sessionmaker[Session], publisher: Publisher,
                 clock: Callable[[], datetime] = utcnow, batch_size: int = 100):
        self._sf = session_factory
        self._publisher = publisher
        self._clock = clock
        self._batch_size = batch_size

    def run_once(self) -> int:
        with self._sf() as session:
            pending = session.execute(
                select(UnitEventRow.id, UnitEventRow.payload)
                .where(UnitEventRow.published_at.is_(None))
                .order_by(UnitEventRow.registry_version)
                .limit(self._batch_size)
            ).all()
        sent = 0
        for event_id, payload in pending:
            self._publisher.publish(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
            with self._sf.begin() as session:
                session.execute(update(UnitEventRow).where(UnitEventRow.id == event_id)
                                .values(published_at=self._clock()))
            sent += 1
        return sent

    def run_forever(self, stop: threading.Event, poll_seconds: float) -> None:
        while not stop.is_set():
            try:
                if self.run_once():
                    logger.info("published unit events")
                self._publisher.heartbeat()
                stop.wait(poll_seconds)
            except Exception:
                logger.exception("outbox relay failed; reconnecting")
                self._publisher.reset()
                stop.wait(min(poll_seconds * 5, 30.0))
