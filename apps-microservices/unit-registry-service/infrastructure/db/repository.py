"""Repositories: rows <-> domain objects. No business rules here."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Collection

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from application.models import UnitType
from unit_registry.types import (
    Unit,
    UnitSource,
    UnitStatus,
    sample_from_dict,
    sample_to_dict,
)

from .models import (
    DimensionUnitTypeRow,
    RegistryMetaRow,
    UnitDimensionRow,
    UnitEventRow,
    UnitRow,
    UnitTypeRow,
)


class UnitRepository:
    def __init__(self, session: Session):
        self._s = session

    # --- registry_meta -------------------------------------------------
    def lock_registry(self) -> int:
        """Row lock on registry_meta: serializes writers so they validate the same state."""
        row = self._s.execute(
            select(RegistryMetaRow).where(RegistryMetaRow.id == 1).with_for_update()
        ).scalar_one()
        return row.registry_version

    def current_version(self) -> int:
        return self._s.execute(
            select(RegistryMetaRow.registry_version).where(RegistryMetaRow.id == 1)
        ).scalar_one()

    def bump_version(self, actor: str, now: datetime) -> int:
        row = self._s.get(RegistryMetaRow, 1)
        row.registry_version += 1
        row.last_bumped_by = actor
        row.last_bumped_at = now
        return row.registry_version

    # --- dimensions ----------------------------------------------------
    def dimension_ids(self) -> dict[str, str]:
        return {name: id_ for id_, name in self._s.execute(select(UnitDimensionRow.id, UnitDimensionRow.name))}

    def _dimension_names(self) -> dict[str, str]:
        return {id_: name for name, id_ in self.dimension_ids().items()}

    # --- units ---------------------------------------------------------
    @staticmethod
    def _to_unit(row: UnitRow, names: dict[str, str]) -> Unit:
        return Unit(
            id=row.id,
            token=row.token,
            dimension=names.get(row.dimension_id) if row.dimension_id else None,
            pint_definition=row.pint_definition,
            aliases=tuple(row.aliases or ()),
            depends_on=tuple(row.depends_on or ()),
            status=UnitStatus(row.status),
            source=UnitSource(row.source),
            sort_order=row.sort_order,
            regression_sample=sample_from_dict(row.regression_sample) if row.regression_sample else None,
            created_by=row.created_by,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def _apply(self, row: UnitRow, unit: Unit) -> None:
        row.token = unit.token
        row.dimension_id = self.dimension_ids()[unit.dimension] if unit.dimension else None
        row.pint_definition = unit.pint_definition
        row.aliases = list(unit.aliases)
        row.depends_on = list(unit.depends_on)
        row.status = unit.status.value
        row.source = unit.source.value
        row.sort_order = unit.sort_order
        row.regression_sample = sample_to_dict(unit.regression_sample) if unit.regression_sample else None
        row.updated_at = unit.updated_at

    def list_units(self, status: UnitStatus | None = None,
                   dimensions: Collection[str] | None = None) -> list[Unit]:
        query = select(UnitRow).order_by(UnitRow.sort_order, UnitRow.token)
        if status is not None:
            query = query.where(UnitRow.status == status.value)
        names = self._dimension_names()
        units = [self._to_unit(row, names) for row in self._s.execute(query).scalars()]
        if dimensions is not None:
            units = [u for u in units if u.dimension in dimensions]
        return units

    def get_unit(self, unit_id: str) -> Unit | None:
        row = self._s.get(UnitRow, unit_id)
        return self._to_unit(row, self._dimension_names()) if row else None

    def get_unit_by_token(self, token: str) -> Unit | None:
        row = self._s.execute(select(UnitRow).where(UnitRow.token == token)).scalar_one_or_none()
        return self._to_unit(row, self._dimension_names()) if row else None

    def insert_unit(self, unit: Unit) -> None:
        row = UnitRow(id=unit.id, created_by=unit.created_by, created_at=unit.created_at)
        self._apply(row, unit)
        self._s.add(row)
        self._s.flush()

    def update_unit(self, unit: Unit) -> None:
        row = self._s.get(UnitRow, unit.id)
        self._apply(row, unit)
        self._s.flush()

    def max_sort_order(self) -> int:
        return self._s.scalar(select(func.coalesce(func.max(UnitRow.sort_order), 0)))

    def active_count(self) -> int:
        return self._s.scalar(select(func.count()).select_from(UnitRow).where(UnitRow.status == "ACTIVE"))

    # --- outbox --------------------------------------------------------
    def insert_event(self, version: int, payload: dict, now: datetime) -> None:
        self._s.add(UnitEventRow(registry_version=version, payload=payload, created_at=now))
        self._s.flush()


class TypeRepository:
    def __init__(self, session: Session):
        self._s = session

    def _links(self) -> dict[str, list[str]]:
        links: dict[str, list[str]] = defaultdict(list)
        query = (
            select(DimensionUnitTypeRow.unit_type_id, UnitDimensionRow.name)
            .join(UnitDimensionRow, UnitDimensionRow.id == DimensionUnitTypeRow.dimension_id)
        )
        for type_id, dimension in self._s.execute(query):
            links[type_id].append(dimension)
        return links

    @staticmethod
    def _to_type(row: UnitTypeRow, links: dict[str, list[str]]) -> UnitType:
        return UnitType(
            id=row.id,
            code=row.code,
            label=row.label,
            description=row.description,
            is_active=row.is_active,
            dimensions=tuple(sorted(links.get(row.id, []))),
            created_by=row.created_by,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def list_types(self, include_inactive: bool = False) -> list[UnitType]:
        query = select(UnitTypeRow).order_by(UnitTypeRow.code)
        if not include_inactive:
            query = query.where(UnitTypeRow.is_active.is_(True))
        links = self._links()
        return [self._to_type(row, links) for row in self._s.execute(query).scalars()]

    def get_type(self, type_id: str) -> UnitType | None:
        row = self._s.get(UnitTypeRow, type_id)
        return self._to_type(row, self._links()) if row else None

    def get_type_by_code(self, code: str) -> UnitType | None:
        row = self._s.execute(select(UnitTypeRow).where(UnitTypeRow.code == code)).scalar_one_or_none()
        return self._to_type(row, self._links()) if row else None

    def insert_type(self, unit_type: UnitType) -> None:
        self._s.add(UnitTypeRow(
            id=unit_type.id, code=unit_type.code, label=unit_type.label,
            description=unit_type.description, is_active=unit_type.is_active,
            created_by=unit_type.created_by, created_at=unit_type.created_at,
            updated_at=unit_type.updated_at,
        ))
        self._s.flush()

    def save_type(self, unit_type: UnitType) -> None:
        row = self._s.get(UnitTypeRow, unit_type.id)
        row.label = unit_type.label
        row.description = unit_type.description
        row.is_active = unit_type.is_active
        row.updated_at = unit_type.updated_at
        self._s.flush()

    def types_by_dimension(self) -> dict[str, list[str]]:
        """{dimension name: sorted ACTIVE type codes} (inactive types are hidden, T3)."""
        result: dict[str, list[str]] = defaultdict(list)
        query = (
            select(UnitDimensionRow.name, UnitTypeRow.code)
            .join(DimensionUnitTypeRow, DimensionUnitTypeRow.dimension_id == UnitDimensionRow.id)
            .join(UnitTypeRow, UnitTypeRow.id == DimensionUnitTypeRow.unit_type_id)
            .where(UnitTypeRow.is_active.is_(True))
        )
        for dimension, code in self._s.execute(query):
            result[dimension].append(code)
        return {dimension: sorted(codes) for dimension, codes in result.items()}

    def set_dimension_types(self, dimension_id: str, type_ids: list[str], actor: str, now: datetime) -> None:
        self._s.execute(delete(DimensionUnitTypeRow).where(DimensionUnitTypeRow.dimension_id == dimension_id))
        for type_id in type_ids:
            self._s.add(DimensionUnitTypeRow(dimension_id=dimension_id, unit_type_id=type_id,
                                             created_by=actor, created_at=now))
        self._s.flush()
