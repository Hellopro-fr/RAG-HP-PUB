"""RegistryBundle: the immutable unit tables one normalize() call reads ([J] §3.3).

A bundle is built off to the side and swapped in by reference; nothing ever calls
define() on a registry that is serving requests (pint is not thread-safe, spec §3.2).
"""
from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Iterable, Mapping, Sequence

import pint

from .legacy import CANONICAL_UNITS, LEGACY_DEFINES, LEGACY_UNIT_TO_DIMENSION
from .types import Unit, UnitStatus


class BundleBuildError(Exception):
    """The unit set cannot produce a consistent registry."""


@dataclass(frozen=True)
class RegistryBundle:
    ureg: pint.UnitRegistry
    unit_to_dimension: Mapping[str, str]
    canonical_units: Mapping[str, str]


def build_bundle(
    defines: Sequence[str],
    unit_to_dimension: Mapping[str, str],
    canonical_units: Mapping[str, str] = CANONICAL_UNITS,
) -> RegistryBundle:
    ureg = pint.UnitRegistry()
    for definition in defines:
        try:
            ureg.define(definition)
        except Exception as exc:  # pint leaks bare TypeError/ValueError for malformed forms
            raise BundleBuildError(f"pint rejected define {definition!r}: {exc}") from exc
    return RegistryBundle(
        ureg=ureg,
        unit_to_dimension=MappingProxyType(dict(unit_to_dimension)),
        canonical_units=MappingProxyType(dict(canonical_units)),
    )


def legacy_bundle() -> RegistryBundle:
    """The frozen in-code tables: fallback floor when the registry is unreachable."""
    return build_bundle(LEGACY_DEFINES, LEGACY_UNIT_TO_DIMENSION)


def explode_lookup_keys(units: Iterable[Unit]) -> dict[str, str]:
    """Flat layer-B index {lowercased spelling: dimension} from active units."""
    index: dict[str, str] = {}
    owner: dict[str, str] = {}
    for unit in units:
        if unit.status is not UnitStatus.ACTIVE or unit.dimension is None:
            continue
        for key in unit.lookup_keys():
            if key in index and index[key] != unit.dimension:
                raise BundleBuildError(
                    f"lookup key {key!r} maps to {index[key]!r} (unit {owner[key]!r}) "
                    f"and to {unit.dimension!r} (unit {unit.token!r})"
                )
            index[key] = unit.dimension
            owner[key] = unit.token
    return index


def active_defines(units: Iterable[Unit]) -> list[str]:
    active = sorted(
        (u for u in units if u.status is UnitStatus.ACTIVE and u.pint_definition),
        key=lambda u: (u.sort_order, u.token),
    )
    return [u.pint_definition for u in active]  # type: ignore[misc]


def bundle_from_units(
    units: Iterable[Unit], canonical_units: Mapping[str, str] = CANONICAL_UNITS
) -> RegistryBundle:
    units = list(units)
    return build_bundle(active_defines(units), explode_lookup_keys(units), canonical_units)
