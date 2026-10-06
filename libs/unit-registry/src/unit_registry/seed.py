"""Seed rows for the `units` table, derived from the frozen legacy tables ([J] §9).

Mapping (proved by tests/test_seed_parity.py against golden.json):
  * every legacy define -> one row: token = the define's name (case kept),
    pint_definition = the define verbatim, sort_order = its position;
  * every legacy unit->dimension key -> sets the dimension of the row whose token
    is exactly that key, or else becomes a lookup-only row (no define).
Aliases stay empty: in the seed, extra spellings live inside the define string
(pint aliases) or as their own lookup-only rows, which keeps parity exact.
"""
from __future__ import annotations

import uuid

from .bundle import explode_lookup_keys
from .legacy import LEGACY_DEFINES, LEGACY_UNIT_TO_DIMENSION
from .types import Unit, UnitSource, UnitStatus

SEED_ACTOR = "seed"
_SEED_NAMESPACE = uuid.UUID("6f1c2a8e-3b7d-4c55-9a51-2f0d7e9b4c10")


class SeedError(Exception):
    """The legacy tables cannot be mapped to seed rows without losing parity."""


def seed_unit_id(token: str) -> str:
    return str(uuid.uuid5(_SEED_NAMESPACE, f"unit:{token}"))


def build_seed_units() -> list[Unit]:
    rows: dict[str, dict] = {}
    order = 0
    for definition in LEGACY_DEFINES:
        name = definition.split("=", 1)[0].strip()
        if name in rows:
            raise SeedError(f"two legacy defines share the name {name!r}")
        rows[name] = {"dimension": None, "pint_definition": definition, "sort_order": order}
        order += 1
    for key, dimension in LEGACY_UNIT_TO_DIMENSION.items():
        row = rows.get(key)
        if row is None:
            rows[key] = {"dimension": dimension, "pint_definition": None, "sort_order": order}
            order += 1
        elif row["dimension"] is None:
            row["dimension"] = dimension
        else:
            raise SeedError(f"lookup key {key!r} appears twice")

    units = [
        Unit(
            id=seed_unit_id(token),
            token=token,
            dimension=row["dimension"],
            pint_definition=row["pint_definition"],
            status=UnitStatus.ACTIVE,
            source=UnitSource.SEED,
            sort_order=row["sort_order"],
            created_by=SEED_ACTOR,
        )
        for token, row in rows.items()
    ]
    if explode_lookup_keys(units) != LEGACY_UNIT_TO_DIMENSION:
        raise SeedError("seed lookup index differs from the legacy unit->dimension table")
    return units
