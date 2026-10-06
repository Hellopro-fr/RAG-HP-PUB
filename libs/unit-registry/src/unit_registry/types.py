"""Domain types shared by unit-registry-service and the normalizer ([J] A.1, P1 subset)."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
from typing import Any


class UnitStatus(str, Enum):
    ACTIVE = "ACTIVE"
    PENDING = "PENDING"
    REJECTED = "REJECTED"
    DISABLED = "DISABLED"


class UnitSource(str, Enum):
    SEED = "seed"
    MANUAL = "manual"
    AUTO_PROPOSAL = "auto_proposal"


@dataclass(frozen=True)
class RegressionSample:
    """G4 sample: replayed through the real engine on every write (spec C7)."""

    label: str
    value: str
    expected_canonical_value: float
    expected_canonical_unit: str
    unit: str | None = None  # None -> the unit's own token
    data_type: str = "numeric"  # "numeric" | "numeric_range"
    expected_canonical_max: float | None = None
    value_max: str | None = None  # numeric_range input max (plan delta P4)


@dataclass(frozen=True)
class Unit:
    id: str
    token: str
    dimension: str | None
    pint_definition: str | None = None  # verbatim ureg.define() string
    aliases: tuple[str, ...] = ()
    depends_on: tuple[str, ...] = ()
    status: UnitStatus = UnitStatus.ACTIVE
    source: UnitSource = UnitSource.MANUAL
    sort_order: int = 0
    regression_sample: RegressionSample | None = None
    created_by: str = ""
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @property
    def define_name(self) -> str | None:
        if not self.pint_definition:
            return None
        return self.pint_definition.split("=", 1)[0].strip()

    def lookup_keys(self) -> list[str]:
        # The engine lowercases the raw unit before the layer-B lookup.
        return [key.lower() for key in (self.token, *self.aliases)]


def sample_to_dict(sample: RegressionSample) -> dict[str, Any]:
    return asdict(sample)


def sample_from_dict(data: dict[str, Any]) -> RegressionSample:
    return RegressionSample(**data)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _parse(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def unit_to_dict(unit: Unit) -> dict[str, Any]:
    return {
        "id": unit.id,
        "token": unit.token,
        "dimension": unit.dimension,
        "pint_definition": unit.pint_definition,
        "aliases": list(unit.aliases),
        "depends_on": list(unit.depends_on),
        "status": unit.status.value,
        "source": unit.source.value,
        "sort_order": unit.sort_order,
        "regression_sample": sample_to_dict(unit.regression_sample) if unit.regression_sample else None,
        "created_by": unit.created_by,
        "created_at": _iso(unit.created_at),
        "updated_at": _iso(unit.updated_at),
    }


def unit_from_dict(data: dict[str, Any]) -> Unit:
    sample = data.get("regression_sample")
    return Unit(
        id=data["id"],
        token=data["token"],
        dimension=data.get("dimension"),
        pint_definition=data.get("pint_definition"),
        aliases=tuple(data.get("aliases") or ()),
        depends_on=tuple(data.get("depends_on") or ()),
        status=UnitStatus(data["status"]),
        source=UnitSource(data["source"]),
        sort_order=int(data.get("sort_order", 0)),
        regression_sample=sample_from_dict(sample) if sample else None,
        created_by=data.get("created_by", ""),
        created_at=_parse(data.get("created_at")),
        updated_at=_parse(data.get("updated_at")),
    )
