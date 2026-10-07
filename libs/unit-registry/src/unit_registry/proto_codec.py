"""Unit <-> unit_registry_pb2 (needs the generated grpc_stubs package)."""
from __future__ import annotations

from datetime import datetime
from typing import Iterable

from grpc_stubs import unit_registry_pb2 as pb

from .types import RegressionSample, Unit, UnitSource, UnitStatus


def _iso(value: datetime | None) -> str:
    return value.isoformat() if value else ""


def _parse(value: str) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def sample_to_proto(sample: RegressionSample) -> pb.RegressionSample:
    message = pb.RegressionSample(
        label=sample.label,
        unit=sample.unit or "",
        value=sample.value,
        data_type=sample.data_type,
        expected_canonical_value=sample.expected_canonical_value,
        expected_canonical_unit=sample.expected_canonical_unit,
    )
    if sample.expected_canonical_max is not None:
        message.expected_canonical_max = sample.expected_canonical_max
    if sample.value_max is not None:
        message.value_max = sample.value_max
    return message


def sample_from_proto(message: pb.RegressionSample) -> RegressionSample:
    return RegressionSample(
        label=message.label,
        value=message.value,
        expected_canonical_value=message.expected_canonical_value,
        expected_canonical_unit=message.expected_canonical_unit,
        unit=message.unit or None,
        data_type=message.data_type or "numeric",
        expected_canonical_max=message.expected_canonical_max if message.HasField("expected_canonical_max") else None,
        value_max=message.value_max if message.HasField("value_max") else None,
    )


def unit_to_proto(unit: Unit, *, registry_version: int = 0, types: Iterable[str] = ()) -> pb.UnitResponse:
    spec = pb.UnitSpec(
        token=unit.token,
        aliases=list(unit.aliases),
        kind="NORMAL",
        pint_definition=unit.pint_definition or "",
        depends_on=list(unit.depends_on),
        dimension=unit.dimension or "",
    )
    if unit.regression_sample is not None:
        spec.regression_sample.CopyFrom(sample_to_proto(unit.regression_sample))
    return pb.UnitResponse(
        id=unit.id,
        spec=spec,
        status=unit.status.value,
        source=unit.source.value,
        created_by=unit.created_by,
        created_at=_iso(unit.created_at),
        updated_at=_iso(unit.updated_at),
        registry_version=registry_version,
        types=list(types),
        sort_order=unit.sort_order,
    )


def unit_from_proto(message: pb.UnitResponse) -> Unit:
    spec = message.spec
    return Unit(
        id=message.id,
        token=spec.token,
        dimension=spec.dimension or None,
        pint_definition=spec.pint_definition or None,
        aliases=tuple(spec.aliases),
        depends_on=tuple(spec.depends_on),
        status=UnitStatus(message.status),
        source=UnitSource(message.source),
        sort_order=message.sort_order,
        regression_sample=sample_from_proto(spec.regression_sample) if spec.HasField("regression_sample") else None,
        created_by=message.created_by,
        created_at=_parse(message.created_at),
        updated_at=_parse(message.updated_at),
    )
