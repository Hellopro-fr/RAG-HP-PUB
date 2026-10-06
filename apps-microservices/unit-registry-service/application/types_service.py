"""Unit types (spec §4.4, C9): open vocabulary linked to dimensions. Metadata only:
no registry_version bump, no outbox row, no event (T5)."""
from __future__ import annotations

import re
import unicodedata
import uuid
from dataclasses import replace
from datetime import datetime
from typing import Any, Callable, Mapping

from sqlalchemy.orm import Session, sessionmaker

from infrastructure.db.repository import TypeRepository, UnitRepository

from .clock import utcnow
from .errors import AlreadyExists, FailedPrecondition, InvalidArgument, NotFound
from .models import UnitType

CODE_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{1,63}$")
_UPDATABLE = frozenset({"label", "description"})


def fold_code(code: str) -> str:
    """Comparison key for near-duplicates: accents and underscores ignored (T1)."""
    stripped = "".join(c for c in unicodedata.normalize("NFKD", code) if not unicodedata.combining(c))
    return stripped.replace("_", "").upper()


class TypeService:
    def __init__(self, session_factory: sessionmaker[Session],
                 clock: Callable[[], datetime] = utcnow,
                 new_id: Callable[[], str] = lambda: str(uuid.uuid4())):
        self._sf = session_factory
        self._clock = clock
        self._new_id = new_id

    def create(self, code: str, label: str, description: str | None, actor: str) -> UnitType:
        code = (code or "").strip()
        label = (label or "").strip()
        if not CODE_PATTERN.fullmatch(code):
            raise InvalidArgument(f"type code {code!r} must match ^[A-Z][A-Z0-9_]{{1,63}}$ (e.g. CAPACITY)")
        if not label:
            raise InvalidArgument("'label' is required")
        now = self._clock()
        with self._sf.begin() as session:
            repo = TypeRepository(session)
            existing = repo.get_type_by_code(code)
            if existing is not None:
                if existing.is_active:
                    raise AlreadyExists(f"type {code} already exists")
                repo.save_type(replace(existing, label=label, description=description,
                                       is_active=True, updated_at=now))  # plan delta P9
                return repo.get_type(existing.id)
            for other in repo.list_types(include_inactive=True):
                if fold_code(other.code) == fold_code(code):
                    state = "" if other.is_active else " (inactive)"
                    raise AlreadyExists(f"type {code} is too close to existing type {other.code}{state}; reuse it")
            unit_type = UnitType(id=self._new_id(), code=code, label=label, description=description,
                                 is_active=True, created_by=actor, created_at=now, updated_at=now)
            repo.insert_type(unit_type)
        return unit_type

    def update(self, type_id: str, changes: Mapping[str, Any], actor: str) -> UnitType:
        if "code" in changes:
            raise InvalidArgument("type code is immutable")
        unknown = sorted(set(changes) - _UPDATABLE)
        if unknown:
            raise InvalidArgument(f"cannot update {', '.join(unknown)}; updatable: label, description")
        if not changes:
            raise InvalidArgument("nothing to update")
        if "label" in changes and not (changes["label"] or "").strip():
            raise InvalidArgument("'label' must not be empty")
        with self._sf.begin() as session:
            repo = TypeRepository(session)
            existing = self._require(repo, type_id)
            fields = {k: (v.strip() if isinstance(v, str) else v) for k, v in changes.items()}
            repo.save_type(replace(existing, updated_at=self._clock(), **fields))
            return repo.get_type(type_id)

    def deactivate(self, type_id: str, actor: str) -> UnitType:
        with self._sf.begin() as session:
            repo = TypeRepository(session)
            existing = self._require(repo, type_id)
            if existing.is_active:
                repo.save_type(replace(existing, is_active=False, updated_at=self._clock()))
            return repo.get_type(type_id)

    def get(self, *, type_id: str | None = None, code: str | None = None) -> UnitType:
        if not type_id and not code:
            raise InvalidArgument("'id' or 'code' is required")
        with self._sf() as session:
            repo = TypeRepository(session)
            found = repo.get_type(type_id) if type_id else repo.get_type_by_code(code)
        if found is None:
            raise NotFound(f"type {type_id or code} not found")
        return found

    def list(self, include_inactive: bool = False) -> list[UnitType]:
        with self._sf() as session:
            return TypeRepository(session).list_types(include_inactive=include_inactive)

    def set_dimension_types(self, dimension: str, codes: list[str], actor: str) -> list[str]:
        with self._sf.begin() as session:
            dimension_ids = UnitRepository(session).dimension_ids()
            if dimension not in dimension_ids:
                raise InvalidArgument(f"unknown dimension {dimension!r}")
            repo = TypeRepository(session)
            type_ids: list[str] = []
            seen: list[str] = []
            for raw in codes:
                code = raw.strip()
                if code in seen:
                    continue
                unit_type = repo.get_type_by_code(code)
                if unit_type is None:
                    raise NotFound(f"type {code} does not exist; create it with create_unit_type first")
                if not unit_type.is_active:
                    raise FailedPrecondition(f"type {code} is inactive")
                type_ids.append(unit_type.id)
                seen.append(code)
            repo.set_dimension_types(dimension_ids[dimension], type_ids, actor, self._clock())
        return sorted(seen)

    @staticmethod
    def _require(repo: TypeRepository, type_id: str) -> UnitType:
        found = repo.get_type(type_id)
        if found is None:
            raise NotFound(f"type {type_id} not found")
        return found
