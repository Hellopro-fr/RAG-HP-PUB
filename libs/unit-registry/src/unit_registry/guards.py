"""Garde-fous G1–G6 ([J] §5), collect-all ([J] B.2). Pure: no DB, no network.

Every guard always reports (the admin UI shows all six). Each pint probe is a fresh
registry built from the other active units, never the serving one.
"""
from __future__ import annotations

import contextlib
import logging
import re
import threading
from dataclasses import dataclass, replace
from typing import Collection, Iterable, Iterator, Mapping, Sequence

from .bundle import BundleBuildError, RegistryBundle, active_defines, build_bundle, bundle_from_units
from .engine import Normalizer
from .legacy import CANONICAL_UNITS, LEGACY_DEFINES
from .types import RegressionSample, Unit, UnitStatus

# The seed already shadows pint built-ins (m, kg, cm, Pa, V, ...): trusted by construction ([J] §5.2 G3).
# Grandfathering is by EXACT definition: a seed name reused with another expression is a redefinition.
GRANDFATHERED_DEFINITIONS = frozenset(LEGACY_DEFINES)
BYPASS_DIMENSIONS = frozenset({"count", "count_rate"})
# Collateral check (G4 + deactivation): every other unit's spellings are replayed with this label/value.
COLLATERAL_LABEL = "Caractéristique technique"
COLLATERAL_VALUE = "2.5"
COLLATERAL_LIST_LIMIT = 5


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
    previous = [u for u in active_units if u.status is UnitStatus.ACTIVE and u.id == candidate.id][:1]
    base_defines = active_defines(others)
    try:
        bundle: RegistryBundle | None = bundle_from_units([*others, candidate], canonical_units)
        bundle_error = ""
    except BundleBuildError as exc:
        bundle, bundle_error = None, str(exc)
    g6 = _g6_uniqueness(candidate, others)
    g3 = _g3_collision(candidate, base_defines)
    g1, probe = _g1_parse(candidate, base_defines)
    g2 = _g2_coherence(candidate, probe, canonical_units, bundle)
    g5 = _skip("G5", "label rules are not dynamic before P2")
    g4, dry_run = _g4_sample(candidate, others, previous, canonical_units, g1.ok and g2.ok and g6.ok,
                             bundle, bundle_error)
    return ValidationOutcome((g1, g2, g3, g4, g5, g6), dry_run)


def _g6_uniqueness(candidate: Unit, others: Sequence[Unit]) -> GuardResult:
    problems = []
    for other in others:
        if other.token == candidate.token:
            problems.append(f"token {candidate.token!r} is already used by unit {other.id}")
        for name in [n for n in candidate.define_names if n in other.define_names]:
            problems.append(f"pint name {name!r} is already defined by unit {other.token!r}")
    taken: dict[str, str] = {}
    for other in others:
        if other.dimension is not None:
            for key in other.lookup_keys():
                taken.setdefault(key, other.token)
    # The engine lowercases the raw unit for the lookup but hands the raw spelling to pint:
    # a pint name "KG" would make the existing spelling "KG" resolve differently (residual R2).
    # Exact seed definitions are trusted (the seed itself has CV/cv, kg/m2 alias + row, ...).
    if candidate.pint_definition not in GRANDFATHERED_DEFINITIONS:
        spelled: dict[str, str] = dict(taken)
        for other in others:
            for name in other.define_names:
                spelled.setdefault(name.lower(), other.token)
        exact = {n for other in others for n in other.define_names}
        for name in candidate.define_names:
            owner = spelled.get(name.lower())
            if owner is not None and name not in exact:
                problems.append(f"pint name {name!r} matches spelling {name.lower()!r} of unit {owner!r} "
                                "(case-insensitive)")
    if candidate.dimension is not None:
        for key in sorted({k for k in candidate.lookup_keys() if k in taken}):
            problems.append(f"lookup key {key!r} already belongs to unit {taken[key]!r}")
    return _fail("G6", "; ".join(problems)) if problems else _ok("G6")


def _g3_collision(candidate: Unit, base_defines: list[str]) -> GuardResult:
    # Every name counts: pint lets the last define win, so "sac = 25 * kilogram = kg"
    # would silently redefine kg (final review C1).
    names = candidate.define_names
    if not names:
        return _skip("G3", "no pint_definition name to check")
    if candidate.pint_definition in GRANDFATHERED_DEFINITIONS:
        return _ok("G3", f"{candidate.pint_definition!r} is a grandfathered seed definition")
    try:
        probe = build_bundle(base_defines, {}).ureg
    except Exception as exc:
        return _fail("G3", f"cannot build the pint probe: {type(exc).__name__}: {exc}")
    lowered = {known.lower(): known for known in probe._units}  # names + aliases (pint 0.24.4, contract-tested)
    problems = []
    for name in names:
        try:
            collides = name in probe
        except Exception as exc:  # a weird name can make pint's parser raise
            problems.append(f"cannot check {name!r} against pint: {type(exc).__name__}: {exc}")
            continue
        if collides:
            problems.append(f"{name!r} already resolves in pint (stored unit, built-in, or prefix "
                            "form such as nm = nano + meter); pick another name")
            continue
        # A case variant of an existing pint name ("Kilogram" vs kilogram) would make a
        # spelling that used to fail resolve to the new unit (residual R2).
        variant = lowered.get(name.lower())
        if variant is not None:
            problems.append(f"{name!r} is a case variant of the pint name {variant!r}; pick another name")
    return _fail("G3", "; ".join(problems)) if problems else _ok("G3")


def _g1_parse(candidate: Unit, base_defines: list[str]):
    if candidate.pint_definition is None:
        return _skip("G1", "no pint_definition"), None
    if "\n" in candidate.pint_definition or "\r" in candidate.pint_definition:
        # pint's define() accepts several lines in one string, so a second line could
        # redefine any built-in (residual R1).
        return _fail("G1", "pint_definition must be one definition on a single line "
                           "(line breaks are not allowed)"), None
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


def _g2_coherence(candidate: Unit, probe, canonical_units: Mapping[str, str],
                  bundle: RegistryBundle | None) -> GuardResult:
    if candidate.dimension is None:
        return _fail("G2", "a dimension is required")
    canonical = canonical_units.get(candidate.dimension)
    if canonical is None:
        return _fail("G2", f"unknown dimension {candidate.dimension!r}; known: {', '.join(sorted(canonical_units))}")
    if candidate.pint_definition is not None:
        if probe is None:
            return _fail("G2", "not checked: G1 failed")
        try:
            (1 * probe[candidate.define_name]).to(canonical)
        except Exception as exc:
            return _fail("G2", f"{candidate.define_name!r} does not convert to {canonical!r} "
                               f"({candidate.dimension}): {type(exc).__name__}: {exc}")
    alias_problems = _alias_problems(candidate, bundle)
    if alias_problems:
        return _fail("G2", "; ".join(alias_problems))
    return _ok("G2") if candidate.pint_definition is not None else _ok("G2", "no pint expression to check")


def _alias_problems(candidate: Unit, bundle: RegistryBundle | None) -> list[str]:
    """An alias only reaches the layer-B lookup; pint must also know it, or it normalizes to nothing (I2)."""
    sample = candidate.regression_sample
    if not candidate.aliases or sample is None or bundle is None:
        return []  # no sample: G4 reports it; no bundle: G4 reports the build error
    normalizer = Normalizer(lambda: bundle)
    try:
        expected = _run_sample(normalizer, replace(sample, unit=None), candidate.token)
    except (TypeError, ValueError):
        return []  # G4 reports an unrunnable sample
    problems = []
    for alias in candidate.aliases:
        got = _run_sample(normalizer, replace(sample, unit=alias), candidate.token)
        if not (_same(got[0], expected[0]) and _same(got[1], expected[1]) and got[2] == expected[2]):
            problems.append(f"alias {alias!r} does not normalize like the token; if pint does not know it, "
                            f'add it as a pint alias in pint_definition ("name = expr = {alias}")')
    return problems


def _g4_sample(candidate: Unit, others: Sequence[Unit], previous: Sequence[Unit],
               canonical_units: Mapping[str, str], prerequisites_ok: bool,
               bundle: RegistryBundle | None, bundle_error: str):
    sample = candidate.regression_sample
    if sample is None:
        return (_fail("G4", "a regression sample is required (it becomes a permanent test)"),
                DryRun(False, error="no sample"))
    if not prerequisites_ok:
        return _fail("G4", "not run: G1, G2 or G6 failed"), DryRun(False, error="not run")
    if bundle is None:
        return (_fail("G4", f"registry does not build with this unit: {bundle_error}"),
                DryRun(False, error=bundle_error))
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
    # Collateral regression (final review C1/I1): no OTHER unit may normalize differently.
    try:
        before = bundle_from_units([*others, *previous], canonical_units)
    except BundleBuildError as exc:
        problems.append(f"current registry does not build, collateral check not run: {exc}")
    else:
        new_names = [n for n in candidate.define_names if n.lower() not in candidate.lookup_keys()]
        changes = _collateral(before, bundle, others, {candidate.id}, new_names)
        if changes:
            problems.append(format_changes(changes))
    return (_fail("G4", "; ".join(problems)) if problems else _ok("G4")), dry_run


def collateral_changes(before_units: Sequence[Unit], after_units: Sequence[Unit],
                       exclude_ids: Collection[str], extra_keys: Iterable[str] = ()) -> list[str]:
    """Spellings of the active units in `before_units` (minus `exclude_ids`), plus `extra_keys`,
    that normalize differently once the registry is rebuilt from `after_units`.
    Each entry: "'key': old -> new"."""
    before = bundle_from_units(before_units)
    after = bundle_from_units(after_units)
    return _collateral(before, after, before_units, exclude_ids, extra_keys)


def format_changes(changes: Sequence[str], limit: int = COLLATERAL_LIST_LIMIT) -> str:
    message = "would change " + ", ".join(changes[:limit])
    if len(changes) > limit:
        message += f" and {len(changes) - limit} more"
    return message


def _collateral(before: RegistryBundle, after: RegistryBundle, units: Sequence[Unit],
                exclude_ids: Collection[str], extra_keys: Iterable[str] = ()) -> list[str]:
    old_n, new_n = Normalizer(lambda: before), Normalizer(lambda: after)
    changes = []
    kept = sorted((u for u in units if u.status is UnitStatus.ACTIVE and u.id not in exclude_ids),
                  key=lambda u: (u.sort_order, u.token))
    with _quiet_engine_warnings():
        # Lowercased lookup keys AND raw (case-preserved) tokens/pint names: pint is case-sensitive.
        keys: dict[str, None] = {}
        for unit in kept:
            for key in sorted({unit.token, *unit.lookup_keys(), *unit.define_names}):
                keys.setdefault(key)
        for key in extra_keys:
            keys.setdefault(key)
        for key in keys:
            old = old_n.normalize(COLLATERAL_LABEL, key, COLLATERAL_VALUE)
            new = new_n.normalize(COLLATERAL_LABEL, key, COLLATERAL_VALUE)
            if old != new:
                changes.append(f"{key!r}: {_describe(old)} -> {_describe(new)}")
    return changes


def _describe(out: Mapping) -> str:
    if not out:
        return "no value"
    return f"{out.get('valeur_canonique')} {out.get('unite_canonique', '')}".strip()


class _CurrentThreadFilter(logging.Filter):
    def __init__(self) -> None:
        super().__init__()
        self._thread = threading.get_ident()

    def filter(self, record: logging.LogRecord) -> bool:
        return record.thread != self._thread


@contextlib.contextmanager
def _quiet_engine_warnings() -> Iterator[None]:
    """The engine logs one root warning per unconvertible spelling; a full replay would log hundreds."""
    root = logging.getLogger()
    flt = _CurrentThreadFilter()
    root.addFilter(flt)
    try:
        yield
    finally:
        root.removeFilter(flt)


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
