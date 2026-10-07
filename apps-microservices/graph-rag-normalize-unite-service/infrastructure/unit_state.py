"""Process-wide unit tables with build-new-then-swap updates (spec §3.2, §5).

Readers call current() once per request and keep that bundle; writers (the event
consumer thread) build a new bundle off to the side and reassign one attribute.
"""
from __future__ import annotations

import threading
import time
from typing import Callable, Iterable, Mapping

from unit_registry.bundle import BundleBuildError, RegistryBundle, bundle_from_units, legacy_bundle
from unit_registry.events import parse_event
from unit_registry.types import Unit, UnitStatus

from .unit_metrics import APPLIED_VERSION, BUILD_FAILURES, BUILD_SECONDS, set_source


class UnitStateHolder:
    def __init__(self, build: Callable[[Iterable[Unit]], RegistryBundle] = bundle_from_units,
                 fallback: Callable[[], RegistryBundle] = legacy_bundle):
        self._build = build
        self._write_lock = threading.Lock()
        self._bundle = fallback()
        self._units: dict[str, Unit] = {}
        self.applied_version = 0
        self.source = "fallback"
        set_source("fallback")

    def current(self) -> RegistryBundle:
        return self._bundle

    def _timed_build(self, units: Iterable[Unit]) -> RegistryBundle:
        started = time.perf_counter()
        try:
            bundle = self._build(list(units))
        except BundleBuildError:
            BUILD_FAILURES.inc()
            raise
        BUILD_SECONDS.observe(time.perf_counter() - started)
        return bundle

    def load_full(self, units: Iterable[Unit], version: int) -> None:
        active = {u.id: u for u in units if u.status is UnitStatus.ACTIVE}
        with self._write_lock:
            bundle = self._timed_build(active.values())
            self._units = active
            self.applied_version = version
            self.source = "db"
            self._bundle = bundle
        APPLIED_VERSION.set(version)
        set_source("db")

    def apply_event(self, event: Mapping) -> str:
        _kind, version, unit = parse_event(event)
        with self._write_lock:
            if self.source != "db":
                return "gap"  # never patch the fallback tables: load from the registry first
            if version <= self.applied_version:
                return "duplicate"
            if version > self.applied_version + 1:
                return "gap"
            units = dict(self._units)
            if unit.status is UnitStatus.ACTIVE:
                units[unit.id] = unit
            else:
                units.pop(unit.id, None)
            bundle = self._timed_build(units.values())  # raises -> state untouched
            self._units = units
            self.applied_version = version
            self._bundle = bundle
        APPLIED_VERSION.set(version)
        return "applied"
