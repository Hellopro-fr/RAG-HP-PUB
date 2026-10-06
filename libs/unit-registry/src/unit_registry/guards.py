"""Garde-fous G1–G6 ([J] §5), collect-all ([J] B.2). Pure: no DB, no network.

Every guard always reports (the admin UI shows all six). Each pint probe is a fresh
registry built from the other active units, never the serving one.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping, Sequence

from .bundle import BundleBuildError, active_defines, build_bundle, bundle_from_units
from .engine import Normalizer
from .legacy import CANONICAL_UNITS, LEGACY_DEFINES
from .types import RegressionSample, Unit, UnitStatus

# The seed already shadows pint built-ins (m, kg, cm, Pa, V, ...): trusted by construction ([J] §5.2 G3).
GRANDFATHERED_DEFINE_NAMES = frozenset(d.split("=", 1)[0].strip() for d in LEGACY_DEFINES)
BYPASS_DIMENSIONS = frozenset({"count", "count_rate"})


@dataclass(frozen=True)
class GuardResult:
    guard: str
    ok: bool
    skipped: bool = False
    message: str = ""


@dataclass(frozen=True)
class DryRun:
    ok: bool
    canonical_value: float | None = None
    canonical_max: float | None = None
    canonical_unit: str = ""
    bypassed: bool = False
    error: str = ""


@dataclass(frozen=True)
class ValidationOutcome:
    guards: tuple[GuardResult, ...]
    dry_run: DryRun

    @property
    def ok(self) -> bool:
        return all(g.ok or g.skipped for g in self.guards)

    @property
    def failures(self) -> tuple[GuardResult, ...]:
        return tuple(g for g in self.guards if not g.ok and not g.skipped)


def _ok(guard: str, message: str = "") -> GuardResult:
    return GuardResult(guard, True, False, message)


def _skip(guard: str, message: str) -> GuardResult:
    return GuardResult(guard, True, True, message)


def _fail(guard: str, message: str) -> GuardResult:
    return GuardResult(guard, False, False, message)


def validate_unit(
    candidate: Unit,
    active_units: Sequence[Unit],
    canonical_units: Mapping[str, str] = CANONICAL_UNITS,
) -> ValidationOutcome:
    others = [u for u in active_units if u.status is UnitStatus.ACTIVE and u.id != candidate.id]
    base_defines = active_defines(others)
    g6 = _g6_uniqueness(candidate, others)
    g3 = _g3_collision(candidate, base_defines)
    g1, probe = _g1_parse(candidate, base_defines)
    g2 = _g2_coherence(candidate, probe, canonical_units)
    g5 = _skip("G5", "label rules are not dynamic before P2")
    g4, dry_run = _g4_sample(candidate, others, canonical_units, g1.ok and g2.ok and g6.ok)
    return ValidationOutcome((g1, g2, g3, g4, g5, g6), dry_run)


def _g6_uniqueness(candidate: Unit, others: Sequence[Unit]) -> GuardResult:
    problems = []
    for other in others:
        if other.token == candidate.token:
            problems.append(f"token {candidate.token!r} is already used by unit {other.id}")
        if candidate.define_name and other.define_name == candidate.define_name:
            problems.append(f"pint name {candidate.define_name!r} is already defined by unit {other.token!r}")
    taken: dict[str, str] = {}
    for other in others:
        if other.dimension is not None:
            for key in other.lookup_keys():
                taken.setdefault(key, other.token)
    if candidate.dimension is not None:
        for key in sorted({k for k in candidate.lookup_keys() if k in taken}):
            problems.append(f"lookup key {key!r} already belongs to unit {taken[key]!r}")
    return _fail("G6", "; ".join(problems)) if problems else _ok("G6")


def _g3_collision(candidate: Unit, base_defines: list[str]) -> GuardResult:
    name = candidate.define_name
    if not name:
        return _skip("G3", "no pint_definition name to check")
    if name in GRANDFATHERED_DEFINE_NAMES:
        return _ok("G3", f"{name!r} is a grandfathered seed name")
    try:
        probe = build_bundle(base_defines, {}).ureg
        collides = name in probe
    except Exception as exc:  # a weird name can make pint's parser raise
        return _fail("G3", f"cannot check {name!r} against pint: {type(exc).__name__}: {exc}")
    if collides:
        return _fail("G3", f"{name!r} already resolves in pint (stored unit, built-in, or prefix "
                           "form such as nm = nano + meter); pick another name")
    return _ok("G3")


def _g1_parse(candidate: Unit, base_defines: list[str]):
    if candidate.pint_definition is None:
        return _skip("G1", "no pint_definition"), None
    name = candidate.define_name
    if not name:
        return _fail("G1", f"{candidate.pint_definition!r} has no unit name before '='"), None
    try:
        probe = build_bundle([*base_defines, candidate.pint_definition], {}).ureg
        (1 * probe[name]).to_base_units()  # define() is lazy: force evaluation
    except Exception as exc:  # includes RecursionError for circular definitions
        return _fail("G1", f"pint cannot evaluate {candidate.pint_definition!r}: "
                           f"{type(exc).__name__}: {exc}"), None
    return _ok("G1"), probe


def _g2_coherence(candidate: Unit, probe, canonical_units: Mapping[str, str]) -> GuardResult:
    if candidate.dimension is None:
        return _fail("G2", "a dimension is required")
    canonical = canonical_units.get(candidate.dimension)
    if canonical is None:
        return _fail("G2", f"unknown dimension {candidate.dimension!r}; known: {', '.join(sorted(canonical_units))}")
    if candidate.pint_definition is None:
        return _ok("G2", "no pint expression to check")
    if probe is None:
        return _fail("G2", "not checked: G1 failed")
    try:
        (1 * probe[candidate.define_name]).to(canonical)
    except Exception as exc:
        return _fail("G2", f"{candidate.define_name!r} does not convert to {canonical!r} "
                           f"({candidate.dimension}): {type(exc).__name__}: {exc}")
    return _ok("G2")


def _g4_sample(candidate: Unit, others: Sequence[Unit], canonical_units: Mapping[str, str],
               prerequisites_ok: bool):
    sample = candidate.regression_sample
    if sample is None:
        return (_fail("G4", "a regression sample is required (it becomes a permanent test)"),
                DryRun(False, error="no sample"))
    if not prerequisites_ok:
        return _fail("G4", "not run: G1, G2 or G6 failed"), DryRun(False, error="not run")
    try:
        bundle = bundle_from_units([*others, candidate], canonical_units)
    except BundleBuildError as exc:
        return _fail("G4", f"registry does not build with this unit: {exc}"), DryRun(False, error=str(exc))
    normalizer = Normalizer(lambda: bundle)
    try:
        value, value_max, unit = _run_sample(normalizer, sample, candidate.token)
    except (TypeError, ValueError) as exc:
        return _fail("G4", f"sample is not runnable: {exc}"), DryRun(False, error=str(exc))

    dry_run = DryRun(
        ok=value is not None,
        canonical_value=value,
        canonical_max=value_max,
        canonical_unit=unit,
        bypassed=candidate.dimension in BYPASS_DIMENSIONS,
        error="" if value is not None else "normalization returned no value",
    )
    problems = []
    if value is None:
        problems.append("normalization returned no value")
    else:
        if not _same(value, sample.expected_canonical_value):
            problems.append(f"got {value} expected {sample.expected_canonical_value}")
        if sample.data_type == "numeric_range" and not _same(value_max, sample.expected_canonical_max):
            problems.append(f"got max {value_max} expected {sample.expected_canonical_max}")
        if unit != sample.expected_canonical_unit:
            problems.append(f"got unit {unit!r} expected {sample.expected_canonical_unit!r}")
    return (_fail("G4", "; ".join(problems)) if problems else _ok("G4")), dry_run


def _run_sample(normalizer: Normalizer, sample: RegressionSample, token: str):
    unit = sample.unit or token
    if sample.data_type == "numeric_range":
        if sample.value_max is None:
            raise ValueError("numeric_range samples need value_max")
        out = normalizer.normalize_range(sample.label, unit, float(sample.value), float(sample.value_max))
        return out.get("valeur_min_canonique"), out.get("valeur_max_canonique"), out.get("unite_canonique", "")
    out = normalizer.normalize(sample.label, unit, sample.value, sample.data_type)
    return out.get("valeur_canonique"), None, out.get("unite_canonique", "")


def _same(got: float | None, expected: float | None) -> bool:
    if got is None or expected is None:
        return got is None and expected is None
    return f"{got:.6g}" == f"{expected:.6g}"


def find_dependents(unit: Unit, remaining: Sequence[Unit]) -> list[Unit]:
    """Active units whose pint definition references `unit`'s define name."""
    name = unit.define_name
    if not name:
        return []
    pattern = re.compile(rf"(?<!\w){re.escape(name)}(?!\w)")
    dependents = []
    for other in remaining:
        if other.id == unit.id or other.status is not UnitStatus.ACTIVE or not other.pint_definition:
            continue
        rhs = other.pint_definition.split("=", 1)[1] if "=" in other.pint_definition else ""
        if name in other.depends_on or pattern.search(rhs):
            dependents.append(other)
    return dependents
