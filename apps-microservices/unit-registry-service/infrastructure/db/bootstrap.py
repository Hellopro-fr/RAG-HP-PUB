"""Idempotent first-boot data ([J] §9.1 "skip if exists")."""
from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from application.models import UnitType
from unit_registry.legacy import CANONICAL_UNITS
from unit_registry.seed import SEED_ACTOR, build_seed_units

from .models import RegistryMetaRow, UnitDimensionRow, UnitRow, UnitTypeRow
from .repository import TypeRepository, UnitRepository

BYPASS_DIMENSIONS = frozenset({"count", "count_rate"})
SEED_TYPES = (("DIMENSION", "Dimension"), ("CAPACITY", "Capacité"))  # no links: operator decision (§4.4)
_NAMESPACE = uuid.UUID("0b8f3d7a-52e1-4c8e-9a3f-7d61c2e4b915")


def _seed_id(kind: str, key: str) -> str:
    return str(uuid.uuid5(_NAMESPACE, f"{kind}:{key}"))


def _empty(session: Session, row) -> bool:
    return not session.scalar(select(func.count()).select_from(row))


def bootstrap(session: Session, now: datetime) -> None:
    if session.get(RegistryMetaRow, 1) is None:
        session.add(RegistryMetaRow(id=1, registry_version=1))
    if _empty(session, UnitDimensionRow):
        for name, canonical in CANONICAL_UNITS.items():
            session.add(UnitDimensionRow(
                id=_seed_id("dimension", name), name=name, canonical_unit=canonical,
                bypass_pint=name in BYPASS_DIMENSIONS, is_active=True,
                created_by=SEED_ACTOR, created_at=now, updated_at=now,
            ))
        session.flush()
    if _empty(session, UnitRow):
        repo = UnitRepository(session)
        for unit in build_seed_units():
            repo.insert_unit(replace(unit, created_at=now, updated_at=now))
    if _empty(session, UnitTypeRow):
        types = TypeRepository(session)
        for code, label in SEED_TYPES:
            types.insert_type(UnitType(id=_seed_id("type", code), code=code, label=label,
                                       description=None, is_active=True, created_by=SEED_ACTOR,
                                       created_at=now, updated_at=now))
    session.flush()
