"""Unit use cases: every write = lock -> guards on the full registry -> row + version + outbox (spec §6)."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any, Callable, Iterable, Mapping

from sqlalchemy.orm import Session, sessionmaker

from infrastructure.db.repository import TypeRepository, UnitRepository
from unit_registry.events import EVENT_CREATED, EVENT_DISABLED, EVENT_UPDATED, make_event
from unit_registry.guards import ValidationOutcome, find_dependents, validate_unit
from unit_registry.types import RegressionSample, Unit, UnitSource, UnitStatus

from .clock import utcnow
from .errors import AlreadyExists, FailedPrecondition, InvalidArgument, NotFound

UPDATABLE_FIELDS = frozenset({"dimension", "pint_definition", "aliases", "depends_on", "regression_sample"})
MAX_TOKEN_LENGTH = 128


@dataclass(frozen=True)
class UnitDraft:
    token: str
    dimension: str | None
    pint_definition: str | None = None
    aliases: tuple[str, ...] = ()
    depends_on: tuple[str, ...] = ()
    regression_sample: RegressionSample | None = None


def _clean_token(token: str) -> str:
    token = (token or "").strip()
    if not token:
        raise InvalidArgument("'token' is required")
    if len(token) > MAX_TOKEN_LENGTH:
        raise InvalidArgument(f"'token' is longer than {MAX_TOKEN_LENGTH} characters")
    return token


def _raise_if_invalid(outcome: ValidationOutcome) -> None:
    if outcome.ok:
        return
    message = "; ".join(f"{g.guard}: {g.message}" for g in outcome.failures)
    if any(g.guard == "G6" for g in outcome.failures):
        raise AlreadyExists(message)
    raise InvalidArgument(message)


def _normalize_changes(changes: Mapping[str, Any]) -> dict[str, Any]:
    unknown = sorted(set(changes) - UPDATABLE_FIELDS)
    if unknown:
        raise InvalidArgument(f"cannot update {', '.join(unknown)}; updatable: {', '.join(sorted(UPDATABLE_FIELDS))}")
    normalized = dict(changes)
    for key in ("aliases", "depends_on"):
        if key in normalized:
            normalized[key] = tuple(normalized[key] or ())
    if "pint_definition" in normalized:
        normalized["pint_definition"] = normalized["pint_definition"] or None
    return normalized


class UnitService:
    def __init__(self, session_factory: sessionmaker[Session],
                 clock: Callable[[], datetime] = utcnow,
                 new_id: Callable[[], str] = lambda: str(uuid.uuid4())):
        self._sf = session_factory
        self._clock = clock
        self._new_id = new_id

    # --- writes ----------------------------------------------------------
    def register(self, draft: UnitDraft, actor: str) -> tuple[Unit, int]:
        token = _clean_token(draft.token)
        if not draft.dimension:
            raise InvalidArgument("'dimension' is required")
        now = self._clock()
        with self._sf.begin() as session:
            repo = UnitRepository(session)
            repo.lock_registry()
            existing = repo.get_unit_by_token(token)
            fields = dict(token=token, dimension=draft.dimension,
                          pint_definition=draft.pint_definition or None,
                          aliases=tuple(draft.aliases), depends_on=tuple(draft.depends_on),
                          regression_sample=draft.regression_sample, status=UnitStatus.ACTIVE,
                          source=UnitSource.MANUAL, updated_at=now)
            if existing is not None and existing.status is UnitStatus.ACTIVE:
                raise AlreadyExists(f"G6: token {token!r} already exists (unit {existing.id}); use update_unit")
            if existing is not None:  # DISABLED or other: reactivate the same row (plan delta P9)
                candidate = replace(existing, **fields)
            else:
                candidate = Unit(id=self._new_id(), sort_order=repo.max_sort_order() + 1,
                                 created_by=actor, created_at=now, **fields)
            _raise_if_invalid(validate_unit(candidate, repo.list_units(status=UnitStatus.ACTIVE)))
            if existing is not None:
                repo.update_unit(candidate)
            else:
                repo.insert_unit(candidate)
            version = repo.bump_version(actor, now)
            repo.insert_event(version, make_event(EVENT_CREATED, version, candidate, now), now)
        return candidate, version

    def update(self, unit_id: str, changes: Mapping[str, Any], actor: str) -> tuple[Unit, int]:
        normalized = _normalize_changes(changes)
        if not normalized:
            raise InvalidArgument("nothing to update")
        now = self._clock()
        with self._sf.begin() as session:
            repo = UnitRepository(session)
            repo.lock_registry()
            existing = repo.get_unit(unit_id)
            if existing is None:
                raise NotFound(f"unit {unit_id!r} not found")
            if existing.status is not UnitStatus.ACTIVE:
                raise FailedPrecondition(
                    f"unit {existing.token!r} is {existing.status.value}; create it again to reactivate it")
            candidate = replace(existing, updated_at=now, **normalized)
            _raise_if_invalid(validate_unit(candidate, repo.list_units(status=UnitStatus.ACTIVE)))
            repo.update_unit(candidate)
            version = repo.bump_version(actor, now)
            repo.insert_event(version, make_event(EVENT_UPDATED, version, candidate, now), now)
        return candidate, version

    def disable(self, unit_id: str, actor: str) -> tuple[Unit, int]:
        now = self._clock()
        with self._sf.begin() as session:
            repo = UnitRepository(session)
            repo.lock_registry()
            existing = repo.get_unit(unit_id)
            if existing is None:
                raise NotFound(f"unit {unit_id!r} not found")
            if existing.status is UnitStatus.DISABLED:
                return existing, repo.current_version()
            remaining = [u for u in repo.list_units(status=UnitStatus.ACTIVE) if u.id != existing.id]
            dependents = find_dependents(existing, remaining)
            if dependents:
                raise FailedPrecondition(
                    f"cannot deactivate {existing.token!r}: still used by "
                    + ", ".join(sorted(u.token for u in dependents)))
            disabled = replace(existing, status=UnitStatus.DISABLED, updated_at=now)
            repo.update_unit(disabled)
            version = repo.bump_version(actor, now)
            repo.insert_event(version, make_event(EVENT_DISABLED, version, disabled, now), now)
        return disabled, version

    # --- reads -----------------------------------------------------------
    def get(self, *, unit_id: str | None = None, token: str | None = None) -> Unit:
        if not unit_id and not token:
            raise InvalidArgument("'id' or 'token' is required")
        with self._sf() as session:
            repo = UnitRepository(session)
            unit = repo.get_unit(unit_id) if unit_id else repo.get_unit_by_token(token)
        if unit is None:
            raise NotFound(f"unit {unit_id or token!r} not found")
        return unit

    def list(self, *, status: UnitStatus | None = None, dimension: str | None = None,
             type_code: str | None = None) -> tuple[list[Unit], int]:
        with self._sf() as session:
            repo = UnitRepository(session)
            dimensions: set[str] | None = {dimension} if dimension else None
            if type_code:
                unit_type = TypeRepository(session).get_type_by_code(type_code)
                if unit_type is None:
                    raise NotFound(f"type {type_code} does not exist")
                linked = set(unit_type.dimensions) if unit_type.is_active else set()
                dimensions = linked if dimensions is None else dimensions & linked
            units = repo.list_units(status=status, dimensions=dimensions)
            version = repo.current_version()
        return units, version

    def validate(self, draft: UnitDraft, *, unit_id: str | None = None) -> ValidationOutcome:
        with self._sf() as session:
            repo = UnitRepository(session)
            active = repo.list_units(status=UnitStatus.ACTIVE)
            fields = dict(token=_clean_token(draft.token), dimension=draft.dimension,
                          pint_definition=draft.pint_definition or None, aliases=tuple(draft.aliases),
                          depends_on=tuple(draft.depends_on), regression_sample=draft.regression_sample)
            if unit_id:
                existing = repo.get_unit(unit_id)
                if existing is None:
                    raise NotFound(f"unit {unit_id!r} not found")
                candidate = replace(existing, **fields)
            else:
                candidate = Unit(id="__candidate__", sort_order=repo.max_sort_order() + 1, **fields)
        return validate_unit(candidate, active)

    def registry_status(self) -> tuple[int, int]:
        with self._sf() as session:
            repo = UnitRepository(session)
            return repo.current_version(), repo.active_count()

    def types_for(self, units: Iterable[Unit]) -> dict[str, list[str]]:
        with self._sf() as session:
            by_dimension = TypeRepository(session).types_by_dimension()
        return {u.id: list(by_dimension.get(u.dimension, [])) for u in units}
