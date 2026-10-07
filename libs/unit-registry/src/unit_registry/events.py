"""Outbox event payloads published on the normalization.units fanout (spec §5)."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping

from .types import Unit, unit_from_dict, unit_to_dict

EVENT_CREATED = "unit.created"
EVENT_UPDATED = "unit.updated"
EVENT_DISABLED = "unit.disabled"
_EVENTS = frozenset({EVENT_CREATED, EVENT_UPDATED, EVENT_DISABLED})


def make_event(event: str, registry_version: int, unit: Unit, occurred_at: datetime) -> dict[str, Any]:
    return {
        "event": event,
        "registry_version": registry_version,
        "unit_id": unit.id,
        "unit": unit_to_dict(unit),
        "occurred_at": occurred_at.isoformat() + "Z",
    }


def parse_event(payload: Mapping[str, Any]) -> tuple[str, int, Unit]:
    try:
        event = payload["event"]
        version = int(payload["registry_version"])
        unit = unit_from_dict(payload["unit"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"malformed unit event: {exc}") from exc
    if event not in _EVENTS:
        raise ValueError(f"unknown unit event {event!r}")
    return event, version, unit
