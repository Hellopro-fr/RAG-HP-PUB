# libs/unit-registry

Shared Python package `unit_registry` used by **unit-registry-service** (writes, validation) and
**graph-rag-normalize-unite-service** (hot path). Spec: `docs/superpowers/specs/2026-10-06-unit-registry-combined-design.md`.

## Modules
- `legacy.py`: frozen tables A/B/C/D moved from the normalizer. Seed source + fallback floor. Never edit to add a unit.
- `types.py`: `Unit`, `RegressionSample`, enums, dict codecs (event payloads).
- `bundle.py`: `RegistryBundle` (pint registry + lookup tables), `bundle_from_units`, `legacy_bundle`.
- `engine.py`: `Normalizer`, the pint engine (moved verbatim; reads one bundle per call).
- `seed.py`: `build_seed_units()` from the legacy tables (233 rows).
- `events.py`: outbox event payloads (`make_event` / `parse_event`).
- `guards.py`: `validate_unit()` G1–G6 (collect-all), `find_dependents()`.
- `proto_codec.py`: `Unit` <-> `unit_registry_pb2`; needs generated `grpc_stubs`, so it is not imported by `__init__`.

## Rules
- pint is pinned to `0.24.4`; `tests/test_pint_contract.py` fails on drift (silent redefinition, lazy define, prefix names).
- Never `define()` on a registry that serves requests: build a new bundle and swap the reference.
- `tests/golden/golden.json` was captured from the pre-move engine. A golden mismatch is a behaviour change, not a fixture to regenerate.

## Tests
`scripts/unit-registry-test.sh libs/unit-registry -q` (persistent container, no local Python needed).
