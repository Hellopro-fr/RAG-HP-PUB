# Unit Registry — Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Units used by `graph-rag-normalize-unite-service` become runtime data. A new `unit-registry-service` owns them in MySQL with CRUD over gRPC, plus unit types. The 5 normalizer replicas hot-reload each change from a RabbitMQ fanout. `mcp-normalize-unite-service` exposes 9 new tools: 4 for units, 5 for unit types.

**Architecture:**
- A new Python lib, `libs/unit-registry`, holds what both services need: the frozen legacy tables, the pint engine (moved out of the normalizer), the bundle builder, the seed and the guards G1–G6. The CRUD service and the normalizer therefore can't disagree.
- `unit-registry-service` validates each write, commits the row, a `registry_version` bump and an outbox event in one transaction, and a relay publishes the event.
- Each normalizer replica patches one unit in its local table, rebuilds a pint registry off to the side, and swaps it in atomically.

**Tech Stack:** Python 3.10, pint 0.24.4, SQLAlchemy 2 + PyMySQL, grpcio, pika, prometheus-client, pydantic-settings, pytest. Go 1.24, grpc-go, protobuf. MySQL 8, RabbitMQ.

**Spec:** `docs/superpowers/specs/2026-10-06-unit-registry-combined-design.md` (approved, including C9 unit types). Read it alongside this plan. Section references below (§4.4, C7, …) point into it.

## Global Constraints

- `pint==0.24.4` exactly, wherever pint is installed (lib `setup.py`, both service `requirements.txt`, the test image).
- Runtime images: `python:3.10-slim` for Python, `golang:1.24-alpine` / `alpine:3.20` for the MCP server (existing).
- `unit-registry-service`: gRPC port **50059**, HTTP port **8571** (`/health`, `/metrics`), compose `expose` only, never `ports`.
- RabbitMQ: exchange **`normalization.units`**, type **fanout**, durable. Each normalizer replica has its own exclusive, auto-delete, server-named queue.
- MySQL database **`normalization_db`**, user **`normalization_user`**, on the existing `mysql` compose service.
- Env var names, exactly:
  - shared: `UNITS_ADMIN_KEY` (≥ 16 chars), `UNIT_REGISTRY_GRPC_ADDR`, `RABBITMQ_URL`, `UNITS_EXCHANGE`;
  - registry service: `MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_DB`;
  - mysql container: `NORMALIZATION_MYSQL_USER`, `NORMALIZATION_MYSQL_PASS`.
- Write RPCs require `authorization: Bearer <UNITS_ADMIN_KEY>`. Reads and `ValidateUnit` are open.
- Identifiers, log messages and error codes are in English. MCP tool descriptions are in French, like the existing `normalize_*` tools. Follow each file's comment language.
- No local Python/Go toolchain: run tests only through `scripts/unit-registry-test.sh` and `scripts/mcp-normalize-test.sh` (created in Tasks 1 and 14), which reuse persistent containers.
- Commits: Conventional Commits with a bilingual EN/FR body, one commit per task, on branch `feat/unit-registry`. The PR targets `features/poc`.
- Never edit `protos/grpc_stubs/graph_normalization.proto`.

## Spec deltas (decided while planning — each is small and recorded here so reviewers don't flag it)

| # | Delta | Reason |
|---|---|---|
| P1 | `units.sort_order BIGINT NOT NULL` added; defines are applied in `(sort_order, token)` order. `UnitResponse.sort_order = 10` added to the proto | Preserves the legacy define order exactly. Replicas need it to rebuild identically |
| P2 | `units.regression_sample` is **nullable**; required (G4) on every manual write, absent on the 233 seed rows | Seed rows can't carry hand-written samples; seed correctness is proven by the golden parity test instead |
| P3 | The pint engine (`normalize`, `normalize_range`, `_get_dimension`) moves verbatim into `libs/unit-registry/engine.py` | G4 must run the *real* engine end-to-end inside the CRUD service |
| P4 | `RegressionSample.value_max` (`optional string = 8`) added | [J]'s sample has an expected max but no input max for `numeric_range` |
| P5 | `DeleteUnitRequest.deleted_by = 2` added | Audit actor, like `created_by` / `updated_by` |
| P6 | `case_sensitive=true` is rejected as P2-only (alongside `kind`, `rewrite_expression`, `label_condition`, `canonical_override`). The MCP `create_unit` has no `case_sensitive` input | The engine lowercases every B lookup; the flag only matters for the E2 `G`/Facteur-G passthrough, which is P2 |
| P7 | `init-db/10_normalization_db.sh` creates the **database and user only**; tables come from `Base.metadata.create_all()` | One DDL source; no drift between SQL and models |
| P8 | `ListUnits` with `limit <= 0` returns every row | Replica resync needs all rows in one call |
| P9 | `create_unit` on a **DISABLED** token reactivates that row (same id). `create_unit_type` on an **inactive** exact code reactivates it | The unique key on `token`/`code` would otherwise make a deactivated unit or type impossible to bring back (§4.4 T3 says "reactivating restores them") |
| P10 | G4 compares values at 6 significant digits on every branch (not `==` on unrounded branches) | One rule; 6 digits is the engine's own rounding |
| P11 | MCP tests use a hand-written fake client (the existing `normalize_test.go` pattern), not bufconn | Consistent with the service's existing tests |

## Review Focus

These are inputs the spec implies but no feature test exercises directly. Each one gets a test in its owning task.

1. **Accent- and case-distinct tokens stay distinct in MySQL.** `Litres` vs `litres` and `décibels` vs `decibels` are separate rows. The unique key must not merge them. Pinned by `test_mysql_collation_keeps_tokens_distinct` (Task 6).
2. **An event reaching a replica that hasn't loaded from the DB yet** (still on the fallback tables) must trigger a full resync, never be applied on top of the fallback. Pinned by `test_event_on_fallback_requests_resync` (Task 12).
3. **Registry reachable but RabbitMQ down at boot.** The replica should still load DB units (best-effort initial resync) instead of serving the fallback indefinitely. Pinned by `test_initial_resync_happens_even_when_rabbitmq_is_down` (Task 12).
4. **Re-creating a token that was deactivated** reactivates the row instead of crashing on the unique key. Pinned by `test_register_reactivates_a_disabled_token` (Task 7).
5. **An agent sends sample numbers as strings** (`"expected_canonical_value": "50"`). They're accepted like JSON numbers. Pinned by `TestCreateUnitAcceptsNumericStringsInSample` (Task 14).

## Facts measured while planning (pint 0.24.4, `python:3.10-slim`, current `features/poc`)

- Legacy tables: 56 defines (unique names), 203 unique unit→dimension keys (204 entries in the literal, one repeated), 99 label rules, 36 canonical units. Every unit→dimension key is already lowercase.
- Seed mapping: 26 keys equal a define name, so the seed has **233** unit rows.
- `UnitRegistry()` never calls `define()` itself. `define("baz = 3 * nonexistent")` is accepted and fails only on use (`UndefinedUnitError`).
- `"foo = = bar"` is accepted *and* evaluates to `1 dimensionless`, so G1 can't catch it, but G2 rejects it for any physical dimension.
- `"nm" in ureg` is `True` (prefix), circular defines raise `RecursionError`, and redefinitions are silently ignored.

---

## File map

```
libs/unit-registry/                          NEW shared lib (package unit_registry)
  setup.py
  test.Dockerfile                            persistent test image (Python side)
  CLAUDE.md
  src/unit_registry/
    __init__.py
    legacy.py                                frozen tables A/B/C/D (moved from the normalizer)
    types.py                                 Unit, RegressionSample, enums, dict codecs
    bundle.py                                RegistryBundle, build_bundle, bundle_from_units, legacy_bundle
    engine.py                                Normalizer (moved engine)
    seed.py                                  build_seed_units()
    events.py                                make_event / parse_event
    guards.py                                validate_unit (G1–G6), find_dependents
    proto_codec.py                           Unit <-> unit_registry_pb2 (imports grpc_stubs)
  tests/
    golden/make_golden.py, golden/golden.json
    test_pint_contract.py, test_legacy_tables.py, test_engine_golden.py, test_types.py,
    test_bundle.py, test_seed_parity.py, test_events.py, test_guards.py, test_proto_codec.py
protos/grpc_stubs/unit_registry.proto        NEW
scripts/unit-registry-test.sh                NEW (pytest in persistent container)
scripts/mcp-normalize-test.sh                NEW (go test in persistent container)
apps-microservices/unit-registry-service/    NEW
  Dockerfile, requirements.txt, CLAUDE.md, init-db/10_normalization_db.sh
  app/__init__.py, app/config.py, app/main.py
  application/__init__.py, clock.py, errors.py, models.py, unit_service.py, types_service.py
  infrastructure/__init__.py
  infrastructure/db/__init__.py, models.py, repository.py, bootstrap.py
  infrastructure/grpc/__init__.py, auth.py, servicer.py, server.py
  infrastructure/messaging/__init__.py, publisher.py, relay.py
  infrastructure/http_server.py
  tests/__init__.py, conftest.py, test_repository.py, test_mysql.py, test_unit_service.py,
        test_types_service.py, test_grpc.py, test_relay.py, test_http_and_config.py
apps-microservices/graph-rag-normalize-unite-service/   MODIFIED
  requirements.txt, Dockerfile, CLAUDE.md, app/config.py, app/main.py
  infrastructure/unit_normalization_service.py  (shrinks to wiring)
  infrastructure/unit_metrics.py, unit_state.py, registry_client.py, unit_events_consumer.py  NEW
  tests/__init__.py, test_unit_state.py, test_unit_events_consumer.py, test_registry_client.py,
        test_use_case_golden.py  NEW
apps-microservices/mcp-normalize-unite-service/         MODIFIED
  Dockerfile, CLAUDE.md, proto/generate.sh, internal/config/config.go, cmd/server/main.go
  internal/tools/registry.go, internal/tools/normalize_test.go (TestToolsList)
  internal/tools/units.go, units_test.go, unit_types.go, unit_types_test.go  NEW
docker-compose.yml                                     MODIFIED
```

---

### Task 1: Test harness + golden oracle captured from the current engine

Before any code moves, record what the normalizer does today. Every later parity check compares against this file.

**Files:**
- Create: `libs/unit-registry/test.Dockerfile`
- Create: `scripts/unit-registry-test.sh`
- Create: `libs/unit-registry/tests/golden/make_golden.py`
- Create (generated): `libs/unit-registry/tests/golden/golden.json`

**Interfaces:**
- Produces: `golden.json` with keys `pint_version`, `defines` (list[str], in order), `unit_to_dimension` (dict), `label_to_dimension` (list of `[keyword, dimension]` pairs, in order), `canonical_units` (dict), `cases` (list of `{"kind": "q"|"r", "label", "unit", "value"|"min"/"max", "data_type"?, "out"}`).
- Produces: `scripts/unit-registry-test.sh <repo-relative-dir> [pytest args]`, which runs pytest in that dir inside container `unit-registry-test`. `PYTHONPATH` is `/stubs` (generated gRPC stubs) + `libs/unit-registry/src` + `libs/common-utils/src`.

- [ ] **Step 1: Create the test image definition**

`libs/unit-registry/test.Dockerfile`:

```dockerfile
# Test image shared by libs/unit-registry, unit-registry-service and
# graph-rag-normalize-unite-service. Built once by scripts/unit-registry-test.sh;
# rebuild with REBUILD=1 when a dependency below changes.
FROM python:3.10-slim
RUN pip install --no-cache-dir \
    pint==0.24.4 \
    "SQLAlchemy==2.0.36" "PyMySQL==1.1.1" cryptography \
    "grpcio==1.68.1" "grpcio-tools==1.68.1" "protobuf>=5.26.1,<6" \
    "pydantic>=2" "pydantic-settings>=2" \
    "pika==1.3.2" prometheus-client waitress redis \
    "pytest==8.3.3"
```

- [ ] **Step 2: Create the runner script**

`scripts/unit-registry-test.sh`:

```bash
#!/usr/bin/env bash
# Run pytest for libs/unit-registry, unit-registry-service or graph-rag-normalize-unite-service
# inside a persistent container (the image is built once, the container is reused).
# Usage: scripts/unit-registry-test.sh <repo-relative-dir> [pytest args...]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
IMAGE=unit-registry-test:py310
NAME=unit-registry-test

if [ "${REBUILD:-0}" = 1 ] || ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  docker build -t "$IMAGE" -f "$ROOT/libs/unit-registry/test.Dockerfile" "$ROOT/libs/unit-registry"
fi

mounted="$(docker inspect -f '{{range .Mounts}}{{if eq .Destination "/repo"}}{{.Source}}{{end}}{{end}}' "$NAME" 2>/dev/null || true)"
running="$(docker inspect -f '{{.State.Running}}' "$NAME" 2>/dev/null || true)"
if [ "$mounted" != "$ROOT" ] || [ "$running" != "true" ]; then
  docker rm -f "$NAME" >/dev/null 2>&1 || true
  docker run -d --name "$NAME" -v "$ROOT:/repo" -w /repo \
    -e PYTHONPATH=/stubs:/repo/libs/unit-registry/src:/repo/libs/common-utils/src \
    "$IMAGE" sleep infinity >/dev/null
fi

# Python gRPC stubs are generated outside the bind mount so the repo stays clean.
docker exec "$NAME" sh -c 'rm -rf /stubs && mkdir -p /stubs \
  && python -m grpc_tools.protoc -I/repo/protos --python_out=/stubs --grpc_python_out=/stubs /repo/protos/grpc_stubs/*.proto \
  && touch /stubs/grpc_stubs/__init__.py'

dir="$1"; shift
docker exec -w "/repo/$dir" "$NAME" python -m pytest "$@"
```

Run: `chmod +x scripts/unit-registry-test.sh`

- [ ] **Step 3: Write the golden capture script**

`libs/unit-registry/tests/golden/make_golden.py`:

```python
"""Capture the CURRENT normalizer's behaviour as the parity oracle (golden.json).

Run ONCE, in plan Task 1, before the engine moves into libs/unit-registry:
    docker exec -w /repo unit-registry-test python libs/unit-registry/tests/golden/make_golden.py

It imports the normalizer service module directly, records every string passed to
UnitRegistry.define while the singleton is built (pint's own __init__ never calls
define, verified on 0.24.4), then replays a corpus of inputs through the engine.
"""
import json
import sys
from pathlib import Path

import pint

REPO = Path(__file__).resolve().parents[4]
SERVICE = REPO / "apps-microservices" / "graph-rag-normalize-unite-service"
OUT = Path(__file__).with_name("golden.json")

recorded: list[str] = []
_original_define = pint.UnitRegistry.define


def _recording_define(self, definition, *args, **kwargs):
    if isinstance(definition, str):
        recorded.append(definition)
    return _original_define(self, definition, *args, **kwargs)


pint.UnitRegistry.define = _recording_define
sys.path.insert(0, str(SERVICE))
from infrastructure.unit_normalization_service import unit_normalizer as legacy  # noqa: E402

pint.UnitRegistry.define = _original_define

LABEL = "Caractéristique technique"

# (label, unit, value[, data_type]) — every special path of normalize().
SPECIAL_QUANTITIES = [
    ("Longueur d'onde", "nm", "532"),
    ("Couple de serrage", "nm", "40"),
    ("Débit", "t/min", "2"),
    ("Régime moteur", "t/min", "1500"),
    ("Niveau sonore", "dB(A)", "65"),
    ("Niveau sonore", "Décibels (dB)", "70"),
    ("Débit d'air", "m³/h", "120"),
    ("Débit d'air", "m3/h", "120"),
    ("Surface", "m²", "3"),
    ("Surface", "m2", "3"),
    ("Densité", "kg/m³", "800"),
    ("Poids", "kg", "+/- 2"),
    ("Poids", "kg", "± 3.5"),
    ("Poids", "kg", "+5"),
    ("Poids", "kg", "abc"),
    ("Poids", "kg", "2", "text"),
    ("Poids", None, "2"),
    ("", "kg", "2"),
    ("Facteur G", "G", "3000"),
    ("Champ magnétique", "G", "3"),
    ("Humidité", "%", "45"),
    ("IRC", "Ra", "80"),
    ("Dureté", "Mohs", "7"),
    ("Epaisseur", "µm", "25"),
    ("Epaisseur", "μm", "25"),
    ("Couple", "N·m", "12"),
    ("Viscosité", "mPa·s", "300"),
    ("Puissance", "KW", "3"),
    ("Puissance", "Watts", "1500"),
    ("Volume", "Litres", "20"),
    ("Poids", "Tonnes", "2"),
    ("Hauteur", "Pieds", "3"),
    ("Vitesse de rotation", "tr/min", "1400"),
    ("Capacité de production", "kg/24h", "500"),
    ("Consommation", "kWh/24h", "1.2"),
    ("Capacité de la batterie", "mAh", "5000"),
    ("Autonomie de la batterie", "heures", "8"),
    ("Mémoire", "Go", "16"),
    ("Charge", "décibels", "3"),
    ("Inconnu", "zzz", "1"),
]

SPECIAL_RANGES = [
    ("Température d'utilisation", "°C", -10.0, 40.0),
    ("Longueur", "cm", 10.0, 50.0),
    ("Poids", "kg", None, 5.0),
    ("Poids", "kg", 1.0, None),
    ("Inconnu", "zzz", 1.0, 2.0),
]


def build_cases() -> list[dict]:
    cases: list[dict] = []

    def q(label, unit, value, data_type="numeric"):
        cases.append(
            {"kind": "q", "label": label, "unit": unit, "value": value, "data_type": data_type}
        )

    for definition in recorded:
        q(LABEL, definition.split("=", 1)[0].strip(), "2.5")
    for key in legacy.UNIT_TO_DIMENSION:
        q(LABEL, key, "2.5")
    for keyword in legacy.LABEL_TO_DIMENSION:
        q(keyword, None, "2.5")
    for args in SPECIAL_QUANTITIES:
        q(*args)
    for label, unit, low, high in SPECIAL_RANGES:
        cases.append({"kind": "r", "label": label, "unit": unit, "min": low, "max": high})
    return cases


def run(case: dict) -> dict:
    if case["kind"] == "q":
        return legacy.normalize(case["label"], case["unit"], case["value"], case["data_type"])
    return legacy.normalize_range(case["label"], case["unit"], case["min"], case["max"])


def main() -> None:
    cases = build_cases()
    for case in cases:
        case["out"] = run(case)
    golden = {
        "pint_version": pint.__version__,
        "defines": recorded,
        "unit_to_dimension": legacy.UNIT_TO_DIMENSION,
        "label_to_dimension": list(legacy.LABEL_TO_DIMENSION.items()),
        "canonical_units": legacy.CANONICAL_UNITS,
        "cases": cases,
    }
    OUT.write_text(json.dumps(golden, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {OUT.name}: {len(recorded)} defines, {len(cases)} cases")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Start the container and generate the oracle**

Run: `scripts/unit-registry-test.sh libs/unit-registry --version` (builds the image and starts the container; prints the pytest version).
Then run: `docker exec -w /repo unit-registry-test python libs/unit-registry/tests/golden/make_golden.py`
Expected: `wrote golden.json: 56 defines, <N> cases` with N ≈ 400.

- [ ] **Step 5: Sanity-check the oracle**

Run: `docker exec -w /repo unit-registry-test python -c "import json; g=json.load(open('libs/unit-registry/tests/golden/golden.json')); print(g['pint_version'], len(g['defines']), len(g['unit_to_dimension']), len(g['label_to_dimension']), len(g['canonical_units']), sum(1 for c in g['cases'] if c['out']))"`
Expected: `0.24.4 56 203 99 36 <M>`, with M > 300.

- [ ] **Step 6: Commit**

```bash
git add libs/unit-registry/test.Dockerfile scripts/unit-registry-test.sh libs/unit-registry/tests/golden/make_golden.py libs/unit-registry/tests/golden/golden.json
git commit -m "test(unit-registry): capture the normalizer's current output as a golden oracle" -m "EN: Records the 56 pint defines, the unit/label/canonical tables and ~400 normalize cases from the untouched engine, plus a persistent pytest container. Every later parity test compares against this file." -m "FR : Enregistre les 56 defines pint, les tables unite/libelle/canonique et ~400 cas de normalize depuis le moteur intact, plus un conteneur pytest persistant. Chaque test de parite ulterieur compare a ce fichier."
```

---

### Task 2: `libs/unit-registry` — legacy tables, types, bundle, engine (moved)

**Files:**
- Create: `libs/unit-registry/setup.py`, `src/unit_registry/__init__.py`, `src/unit_registry/legacy.py` (generated), `src/unit_registry/types.py`, `src/unit_registry/bundle.py`, `src/unit_registry/engine.py`, `libs/unit-registry/CLAUDE.md`
- Create: `libs/unit-registry/tests/test_pint_contract.py`, `test_legacy_tables.py`, `test_engine_golden.py`, `test_types.py`, `test_bundle.py`
- Temporary (deleted before commit): `libs/unit-registry/extract_legacy_tables.py`

**Interfaces:**
- Produces `unit_registry.legacy`: `LEGACY_DEFINES: tuple[str, ...]`, `LEGACY_UNIT_TO_DIMENSION: dict[str, str]`, `LABEL_TO_DIMENSION: dict[str, str]` (ordered), `CANONICAL_UNITS: dict[str, str]`.
- Produces `unit_registry.types`: `UnitStatus`, `UnitSource`, `RegressionSample`, `Unit` (with `.define_name`, `.lookup_keys()`), `sample_to_dict`, `sample_from_dict`, `unit_to_dict`, `unit_from_dict`.
- Produces `unit_registry.bundle`: `BundleBuildError`, `RegistryBundle(ureg, unit_to_dimension, canonical_units)`, `build_bundle(defines, unit_to_dimension, canonical_units=CANONICAL_UNITS)`, `legacy_bundle()`, `explode_lookup_keys(units) -> dict[str, str]`, `active_defines(units) -> list[str]`, `bundle_from_units(units, canonical_units=CANONICAL_UNITS)`.
- Produces `unit_registry.engine.Normalizer(bundle_provider: Callable[[], RegistryBundle])` with `normalize(label, unit, value, data_type="numeric") -> dict` and `normalize_range(label, unit, min_val, max_val) -> dict`. Same outputs as today.

- [ ] **Step 1: Write the failing tests**

`libs/unit-registry/tests/test_pint_contract.py`:

```python
"""Pins the pint 0.24.4 behaviours the registry design relies on (spec §2, [J] D12)."""
import pint
import pytest


def test_pint_is_pinned():
    assert pint.__version__ == "0.24.4"


def test_redefinition_is_silently_ignored():
    ureg = pint.UnitRegistry()
    ureg.define("galette = count")
    ureg.define("galette = 2 * count")
    assert ureg.Quantity(3, "galette").to("count").magnitude == 3


def test_define_is_lazy_so_validation_must_force_evaluation():
    ureg = pint.UnitRegistry()
    ureg.define("baz = 3 * nonexistent")  # accepted
    with pytest.raises(pint.errors.UndefinedUnitError):
        (1 * ureg["baz"]).to_base_units()


def test_prefix_forms_count_as_existing_names():
    assert "nm" in pint.UnitRegistry()  # nano + meter: the G3 trap


def test_there_is_no_public_unit_removal():
    names = dir(pint.UnitRegistry())
    assert "undefine" not in names and "remove_unit" not in names


def test_circular_definitions_raise_instead_of_hanging():
    ureg = pint.UnitRegistry()
    ureg.define("cyc_a = 2 * cyc_b")
    ureg.define("cyc_b = 3 * cyc_a")
    with pytest.raises(RecursionError):
        (1 * ureg["cyc_a"]).to_base_units()
```

`libs/unit-registry/tests/test_legacy_tables.py`:

```python
import json
from pathlib import Path

from unit_registry.legacy import (
    CANONICAL_UNITS,
    LABEL_TO_DIMENSION,
    LEGACY_DEFINES,
    LEGACY_UNIT_TO_DIMENSION,
)

GOLDEN = json.loads((Path(__file__).parent / "golden" / "golden.json").read_text(encoding="utf-8"))


def test_defines_match_the_recorded_order():
    assert list(LEGACY_DEFINES) == GOLDEN["defines"]


def test_unit_to_dimension_matches():
    assert LEGACY_UNIT_TO_DIMENSION == GOLDEN["unit_to_dimension"]


def test_label_rules_match_in_order():
    assert [list(p) for p in LABEL_TO_DIMENSION.items()] == GOLDEN["label_to_dimension"]


def test_canonical_units_match():
    assert CANONICAL_UNITS == GOLDEN["canonical_units"]
```

`libs/unit-registry/tests/test_engine_golden.py`:

```python
import json
from pathlib import Path

import pytest

from unit_registry.bundle import legacy_bundle
from unit_registry.engine import Normalizer

GOLDEN = json.loads((Path(__file__).parent / "golden" / "golden.json").read_text(encoding="utf-8"))


def run_case(normalizer: Normalizer, case: dict) -> dict:
    if case["kind"] == "q":
        return normalizer.normalize(case["label"], case["unit"], case["value"], case["data_type"])
    return normalizer.normalize_range(case["label"], case["unit"], case["min"], case["max"])


@pytest.fixture(scope="module")
def legacy_normalizer() -> Normalizer:
    bundle = legacy_bundle()
    return Normalizer(lambda: bundle)


def test_moved_engine_reproduces_every_golden_case(legacy_normalizer):
    mismatches = []
    for case in GOLDEN["cases"]:
        got = run_case(legacy_normalizer, case)
        if got != case["out"]:
            mismatches.append({"case": case, "got": got})
    assert not mismatches, mismatches[:5]
```

`libs/unit-registry/tests/test_types.py`:

```python
from datetime import datetime

from unit_registry.types import (
    RegressionSample,
    Unit,
    UnitSource,
    UnitStatus,
    unit_from_dict,
    unit_to_dict,
)


def make_unit(**overrides) -> Unit:
    base = dict(
        id="u1",
        token="Sac",
        dimension="mass",
        pint_definition="sac_ciment = 25 * kilogram = sacs",
        aliases=("SACS",),
        depends_on=(),
        status=UnitStatus.ACTIVE,
        source=UnitSource.MANUAL,
        sort_order=7,
        regression_sample=RegressionSample(
            label="Poids", value="2", expected_canonical_value=50.0, expected_canonical_unit="kilogram"
        ),
        created_by="tester",
        created_at=datetime(2026, 10, 6, 12, 0, 0),
        updated_at=datetime(2026, 10, 6, 12, 0, 0),
    )
    base.update(overrides)
    return Unit(**base)


def test_define_name_is_the_text_before_the_first_equals():
    assert make_unit().define_name == "sac_ciment"
    assert make_unit(pint_definition=None).define_name is None


def test_lookup_keys_are_token_and_aliases_lowercased():
    assert make_unit().lookup_keys() == ["sac", "sacs"]


def test_dict_round_trip_is_lossless():
    unit = make_unit()
    assert unit_from_dict(unit_to_dict(unit)) == unit


def test_dict_round_trip_without_sample_or_dates():
    unit = make_unit(regression_sample=None, created_at=None, updated_at=None)
    assert unit_from_dict(unit_to_dict(unit)) == unit
```

`libs/unit-registry/tests/test_bundle.py`:

```python
from types import MappingProxyType

import pytest

from unit_registry.bundle import (
    BundleBuildError,
    active_defines,
    build_bundle,
    bundle_from_units,
    explode_lookup_keys,
)
from unit_registry.types import Unit, UnitStatus


def unit(token, dimension=None, define=None, aliases=(), sort_order=0, status=UnitStatus.ACTIVE):
    return Unit(id=f"id-{token}", token=token, dimension=dimension, pint_definition=define,
                aliases=tuple(aliases), sort_order=sort_order, status=status)


def test_explode_maps_token_and_aliases_lowercased():
    index = explode_lookup_keys([unit("Sac", "mass", aliases=["SACS"]), unit("KW")])
    assert index == {"sac": "mass", "sacs": "mass"}


def test_explode_skips_disabled_units():
    assert explode_lookup_keys([unit("sac", "mass", status=UnitStatus.DISABLED)]) == {}


def test_explode_rejects_one_key_with_two_dimensions():
    with pytest.raises(BundleBuildError, match="'sac'"):
        explode_lookup_keys([unit("sac", "mass"), unit("x", "volume", aliases=["sac"])])


def test_active_defines_follow_sort_order():
    units = [unit("b", define="b_u = 2 * meter", sort_order=2), unit("a", define="a_u = meter", sort_order=1)]
    assert active_defines(units) == ["a_u = meter", "b_u = 2 * meter"]


def test_build_bundle_wraps_pint_errors():
    with pytest.raises(BundleBuildError, match="z = \\(3"):
        build_bundle(["z = (3"], {})


def test_bundle_tables_are_read_only():
    bundle = bundle_from_units([unit("sac", "mass", define="sac = 25 * kilogram")])
    assert isinstance(bundle.unit_to_dimension, MappingProxyType)
    with pytest.raises(TypeError):
        bundle.unit_to_dimension["x"] = "mass"  # type: ignore[index]
    assert bundle.ureg.Quantity(2, "sac").to("kilogram").magnitude == 50
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `scripts/unit-registry-test.sh libs/unit-registry -q`
Expected: collection errors such as `ModuleNotFoundError: No module named 'unit_registry'`. The pint contract tests pass.

- [ ] **Step 3: Create the package skeleton**

`libs/unit-registry/setup.py`:

```python
from setuptools import find_packages, setup

setup(
    name="unit-registry",
    version="0.1.0",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    install_requires=["pint==0.24.4"],
)
```

`libs/unit-registry/src/unit_registry/__init__.py`:

```python
"""Shared unit-registry domain: legacy tables, pint engine, bundle builder, seed and guards.

proto_codec is deliberately not imported here: it needs the generated grpc_stubs.
"""
```

- [ ] **Step 4: Generate `legacy.py` from the normalizer source**

Create the temporary script `libs/unit-registry/extract_legacy_tables.py`:

```python
"""One-off (plan Task 2): write unit_registry/legacy.py from the normalizer's hard-coded tables.

Defines are extracted in source order with ast; the three dict literals are copied as
text so their FIX-history comments survive. Delete this script after running it.
"""
import ast
import textwrap
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "apps-microservices/graph-rag-normalize-unite-service/infrastructure/unit_normalization_service.py"
OUT = REPO / "libs/unit-registry/src/unit_registry/legacy.py"

HEADER = '''"""Frozen copy of the hard-coded unit tables (layers A, B, C, D of [J] §1.1).

Moved verbatim from graph-rag-normalize-unite-service/infrastructure/unit_normalization_service.py
(plan Task 2). Roles: seed source (seed.py), boot-time fallback floor (bundle.legacy_bundle),
and parity oracle input. Do NOT edit to add a unit: units are managed by unit-registry-service.
LABEL_TO_DIMENSION (layer C) is still read by the engine directly until P2.
"""

'''
TARGETS = {
    "UNIT_TO_DIMENSION": "LEGACY_UNIT_TO_DIMENSION",
    "LABEL_TO_DIMENSION": "LABEL_TO_DIMENSION",
    "CANONICAL_UNITS": "CANONICAL_UNITS",
}

text = SRC.read_text(encoding="utf-8")
lines = text.splitlines()
tree = ast.parse(text)

define_calls = sorted(
    (n for n in ast.walk(tree)
     if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "define"),
    key=lambda n: (n.lineno, n.col_offset),
)
defines = [call.args[0].value for call in define_calls]

blocks = {}
for node in ast.walk(tree):
    if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Attribute):
        attr = node.targets[0].attr
        if attr in TARGETS:
            chunk = textwrap.dedent("\n".join(lines[node.lineno - 1:node.end_lineno]))
            old = f"cls._instance.{attr} = {{"
            assert chunk.startswith(old), chunk[:80]
            blocks[attr] = chunk.replace(old, f"{TARGETS[attr]}: dict[str, str] = {{", 1)

assert len(defines) == 56 and set(blocks) == set(TARGETS), (len(defines), sorted(blocks))
body = HEADER + "LEGACY_DEFINES: tuple[str, ...] = (\n"
body += "".join(f"    {d!r},\n" for d in defines)
body += ")\n\n" + "\n\n".join(blocks[k] for k in TARGETS) + "\n"
OUT.write_text(body, encoding="utf-8")
print(f"wrote {OUT} ({len(defines)} defines)")
```

Run: `docker exec -w /repo unit-registry-test python libs/unit-registry/extract_legacy_tables.py`
Expected: `wrote /repo/libs/unit-registry/src/unit_registry/legacy.py (56 defines)`
Then: `rm libs/unit-registry/extract_legacy_tables.py`

- [ ] **Step 5: Write `types.py`**

`libs/unit-registry/src/unit_registry/types.py`:

```python
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
```

- [ ] **Step 6: Write `bundle.py`**

`libs/unit-registry/src/unit_registry/bundle.py`:

```python
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
```

- [ ] **Step 7: Move the engine into `engine.py`**

Create `libs/unit-registry/src/unit_registry/engine.py` with this header:

```python
"""pint normalization engine, moved verbatim from graph-rag-normalize-unite-service (plan Task 2).

The only change: unit tables come from a RegistryBundle fetched ONCE per normalize()
call, so a concurrent swap never mixes two registries inside one call. Layer C
(LABEL_TO_DIMENSION) and the sanitize chain stay in code until P2 (spec §8).
"""
import logging
import re
import unicodedata
from typing import Any, Callable, Dict, Optional

from .bundle import RegistryBundle
from .legacy import LABEL_TO_DIMENSION


class Normalizer:
    LABEL_TO_DIMENSION = LABEL_TO_DIMENSION

    def __init__(self, bundle_provider: Callable[[], RegistryBundle]):
        self._bundle_provider = bundle_provider
```

Then copy lines **585–968** of `apps-microservices/graph-rag-normalize-unite-service/infrastructure/unit_normalization_service.py` (from `    @staticmethod` above `_strip_accents` through the last line of `normalize_range`) into the class body, keeping their 4-space indentation. Apply exactly these edits to the copied text:

1. `def _get_dimension(self, unit: Optional[str], label: str) -> Optional[str]:` → `def _get_dimension(self, unit: Optional[str], label: str, bundle: RegistryBundle) -> Optional[str]:`
2. Both `self.UNIT_TO_DIMENSION` inside `_get_dimension` → `bundle.unit_to_dimension`
3. In `normalize`, immediately after the docstring, insert the line `        bundle = self._bundle_provider()`
4. `dimension = self._get_dimension(original_unit, label)` → `dimension = self._get_dimension(original_unit, label, bundle)`
5. Both `self.CANONICAL_UNITS` → `bundle.canonical_units`
6. `self.ureg.Quantity(` → `bundle.ureg.Quantity(`

`self.LABEL_TO_DIMENSION` stays as it is (class attribute).

Run: `grep -nE "self\.(ureg|UNIT_TO_DIMENSION|CANONICAL_UNITS)" libs/unit-registry/src/unit_registry/engine.py`
Expected: no output.

- [ ] **Step 8: Run the tests to verify they pass**

Run: `scripts/unit-registry-test.sh libs/unit-registry -q`
Expected: all tests in the 5 files pass (≈ 21 tests).

- [ ] **Step 9: Write the lib's `CLAUDE.md`**

`libs/unit-registry/CLAUDE.md`:

```markdown
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
```

- [ ] **Step 10: Commit**

```bash
git add libs/unit-registry
git commit -m "feat(unit-registry): shared lib with legacy tables, bundle builder and the moved pint engine" -m "EN: Moves the normalizer's hard-coded tables and normalize() engine verbatim into libs/unit-registry; the engine now reads one RegistryBundle per call. Golden test proves identical output; pint pinned to 0.24.4 with a behaviour contract test." -m "FR : Deplace tel quel les tables codees en dur et le moteur normalize() du normaliseur dans libs/unit-registry ; le moteur lit un RegistryBundle par appel. Le test golden prouve une sortie identique ; pint epingle en 0.24.4 avec un test de contrat."
```

---

### Task 3: Seed builder + parity gate

**Files:**
- Create: `libs/unit-registry/src/unit_registry/seed.py`
- Create: `libs/unit-registry/tests/test_seed_parity.py`

**Interfaces:**
- Consumes: `legacy.*`, `types.Unit`, `bundle.explode_lookup_keys`, `bundle.active_defines`, `bundle.bundle_from_units`, `engine.Normalizer`.
- Produces: `unit_registry.seed.build_seed_units() -> list[Unit]` (deterministic ids via uuid5, `source=SEED`, `created_by="seed"`, no timestamps), `seed.SeedError`, `seed.SEED_ACTOR`, `seed.seed_unit_id(token) -> str`.

- [ ] **Step 1: Write the failing test**

`libs/unit-registry/tests/test_seed_parity.py`:

```python
import json
from pathlib import Path

import pytest

from unit_registry.bundle import active_defines, bundle_from_units, explode_lookup_keys
from unit_registry.engine import Normalizer
from unit_registry.legacy import LEGACY_DEFINES, LEGACY_UNIT_TO_DIMENSION
from unit_registry.seed import build_seed_units
from unit_registry.types import UnitSource, UnitStatus

GOLDEN = json.loads((Path(__file__).parent / "golden" / "golden.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def seed():
    return build_seed_units()


def test_every_define_becomes_one_row_in_order(seed):
    assert sum(1 for u in seed if u.pint_definition) == len(LEGACY_DEFINES)
    assert active_defines(seed) == list(LEGACY_DEFINES)


def test_row_count_is_defines_plus_unmatched_keys(seed):
    names = {d.split("=", 1)[0].strip() for d in LEGACY_DEFINES}
    unmatched = [k for k in LEGACY_UNIT_TO_DIMENSION if k not in names]
    assert len(seed) == len(LEGACY_DEFINES) + len(unmatched)


def test_exploded_lookup_index_equals_the_legacy_dict(seed):
    assert explode_lookup_keys(seed) == LEGACY_UNIT_TO_DIMENSION


def test_seed_rows_are_active_seed_rows_with_unique_tokens(seed):
    assert all(u.status is UnitStatus.ACTIVE and u.source is UnitSource.SEED for u in seed)
    assert len({u.token for u in seed}) == len(seed)
    assert len({u.id for u in seed}) == len(seed)


def test_seed_is_deterministic(seed):
    assert build_seed_units() == seed


def test_seed_built_bundle_reproduces_every_golden_case(seed):
    bundle = bundle_from_units(seed)
    normalizer = Normalizer(lambda: bundle)
    mismatches = []
    for case in GOLDEN["cases"]:
        if case["kind"] == "q":
            got = normalizer.normalize(case["label"], case["unit"], case["value"], case["data_type"])
        else:
            got = normalizer.normalize_range(case["label"], case["unit"], case["min"], case["max"])
        if got != case["out"]:
            mismatches.append({"case": case, "got": got})
    assert not mismatches, mismatches[:5]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `scripts/unit-registry-test.sh libs/unit-registry -q tests/test_seed_parity.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'unit_registry.seed'`.

- [ ] **Step 3: Write `seed.py`**

`libs/unit-registry/src/unit_registry/seed.py`:

```python
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `scripts/unit-registry-test.sh libs/unit-registry -q`
Expected: all tests pass, including the 6 seed tests.

- [ ] **Step 5: Commit**

```bash
git add libs/unit-registry/src/unit_registry/seed.py libs/unit-registry/tests/test_seed_parity.py
git commit -m "feat(unit-registry): seed rows from the legacy tables with a parity gate" -m "EN: build_seed_units() maps the 56 defines and 203 lookup keys to 233 unit rows; a bundle built from the seed reproduces every golden case and the exact legacy lookup index." -m "FR : build_seed_units() transforme les 56 defines et 203 cles de recherche en 233 lignes d'unite ; un bundle construit depuis le seed reproduit chaque cas golden et l'index de recherche legacy a l'identique."
```

---

### Task 4: Guards G1–G6, dependents, events

**Files:**
- Create: `libs/unit-registry/src/unit_registry/guards.py`, `libs/unit-registry/src/unit_registry/events.py`
- Create: `libs/unit-registry/tests/test_guards.py`, `libs/unit-registry/tests/test_events.py`

**Interfaces:**
- Produces `unit_registry.guards`:
  - `GuardResult(guard, ok, skipped=False, message="")`
  - `DryRun(ok, canonical_value=None, canonical_max=None, canonical_unit="", bypassed=False, error="")`
  - `ValidationOutcome(guards: tuple[GuardResult, ...], dry_run)`, with properties `.ok` and `.failures`. `guards` always has 6 entries in order G1..G6.
  - `validate_unit(candidate: Unit, active_units: Sequence[Unit], canonical_units=CANONICAL_UNITS) -> ValidationOutcome`
  - `find_dependents(unit: Unit, remaining: Sequence[Unit]) -> list[Unit]`
  - `GRANDFATHERED_DEFINE_NAMES: frozenset[str]`
- Produces `unit_registry.events`:
  - constants `EVENT_CREATED = "unit.created"`, `EVENT_UPDATED = "unit.updated"`, `EVENT_DISABLED = "unit.disabled"`
  - `make_event(event: str, registry_version: int, unit: Unit, occurred_at: datetime) -> dict`
  - `parse_event(payload: Mapping) -> tuple[str, int, Unit]`, which raises `ValueError` on a malformed payload.

- [ ] **Step 1: Write the failing tests**

`libs/unit-registry/tests/test_guards.py`:

```python
import pytest

from unit_registry.guards import find_dependents, validate_unit
from unit_registry.seed import build_seed_units
from unit_registry.types import RegressionSample, Unit, UnitSource


@pytest.fixture(scope="module")
def seed():
    return build_seed_units()


def sample(value="2", expected=50.0, unit_out="kilogram", label="Poids", **kw):
    return RegressionSample(label=label, value=value, expected_canonical_value=expected,
                            expected_canonical_unit=unit_out, **kw)


def candidate(**overrides) -> Unit:
    base = dict(id="new", token="sac_ciment", dimension="mass",
                pint_definition="sac_ciment = 25 * kilogram", source=UnitSource.MANUAL,
                sort_order=10_000, regression_sample=sample())
    base.update(overrides)
    return Unit(**base)


def by_guard(outcome):
    return {g.guard: g for g in outcome.guards}


def test_valid_unit_passes_all_guards(seed):
    outcome = validate_unit(candidate(), seed)
    assert outcome.ok, outcome.failures
    assert [g.guard for g in outcome.guards] == ["G1", "G2", "G3", "G4", "G5", "G6"]
    assert by_guard(outcome)["G5"].skipped
    assert outcome.dry_run.ok and outcome.dry_run.canonical_value == 50.0


def test_g1_catches_the_lazy_define_trap(seed):
    outcome = validate_unit(candidate(token="baz_x", pint_definition="baz_x = 3 * nonexistent_y"), seed)
    assert not by_guard(outcome)["G1"].ok
    assert "UndefinedUnitError" in by_guard(outcome)["G1"].message


@pytest.mark.parametrize("bad", ["z_u = (3", "q_only", "= meter"])
def test_g1_rejects_malformed_defines(seed, bad):
    outcome = validate_unit(candidate(token="weird", pint_definition=bad), seed)
    assert not by_guard(outcome)["G1"].ok


def test_g2_catches_a_dimensionless_define_that_g1_accepts(seed):
    # pint 0.24.4 evaluates "foo_u = = bar" to 1 dimensionless: only G2 stops it.
    outcome = validate_unit(candidate(token="foo_u", pint_definition="foo_u = = bar"), seed)
    assert by_guard(outcome)["G1"].ok and not by_guard(outcome)["G2"].ok


def test_g1_rejects_circular_definitions(seed):
    others = [*seed, Unit(id="c1", token="cyc_b", dimension=None,
                          pint_definition="cyc_b = 3 * cyc_a", sort_order=9_999)]
    outcome = validate_unit(candidate(token="cyc_a", pint_definition="cyc_a = 2 * cyc_b"), others)
    assert not by_guard(outcome)["G1"].ok


def test_g2_rejects_an_unknown_dimension(seed):
    outcome = validate_unit(candidate(dimension="weight"), seed)
    assert "unknown dimension 'weight'" in by_guard(outcome)["G2"].message


def test_g2_rejects_a_define_in_the_wrong_dimension(seed):
    outcome = validate_unit(candidate(dimension="volume"), seed)
    assert not by_guard(outcome)["G2"].ok


def test_g3_rejects_a_prefix_collision(seed):
    outcome = validate_unit(candidate(token="nmx", pint_definition="nm = newton * meter",
                                      dimension="torque"), seed)
    assert not by_guard(outcome)["G3"].ok


def test_g3_grandfathers_seed_names(seed):
    kg = next(u for u in seed if u.token == "kg")
    outcome = validate_unit(kg, seed)
    assert by_guard(outcome)["G3"].ok


def test_g4_requires_a_sample(seed):
    outcome = validate_unit(candidate(regression_sample=None), seed)
    assert "regression sample is required" in by_guard(outcome)["G4"].message


def test_g4_rejects_a_wrong_expected_value(seed):
    outcome = validate_unit(candidate(regression_sample=sample(expected=40.0)), seed)
    g4 = by_guard(outcome)["G4"]
    assert not g4.ok and "expected 40.0" in g4.message
    assert outcome.dry_run.canonical_value == 50.0


def test_g4_compares_at_six_significant_digits(seed):
    outcome = validate_unit(candidate(regression_sample=sample(expected=50.0000001)), seed)
    assert by_guard(outcome)["G4"].ok


def test_g4_runs_range_samples(seed):
    s = sample(value="1", value_max="3", expected=25.0, expected_canonical_max=75.0,
               data_type="numeric_range")
    assert validate_unit(candidate(regression_sample=s), seed).ok


def test_g6_rejects_an_existing_token(seed):
    outcome = validate_unit(candidate(token="kg", pint_definition=None), seed)
    assert not by_guard(outcome)["G6"].ok


def test_g6_rejects_an_alias_that_is_already_a_lookup_key(seed):
    outcome = validate_unit(candidate(aliases=("KG",)), seed)
    assert "lookup key 'kg'" in by_guard(outcome)["G6"].message


def test_update_of_itself_is_not_a_collision(seed):
    first = candidate(id="same")
    assert validate_unit(candidate(id="same", pint_definition="sac_ciment = 20 * kilogram",
                                   regression_sample=sample(expected=40.0)), [*seed, first]).ok


def test_find_dependents_reports_units_built_on_a_define(seed):
    cheval_vapeur = next(u for u in seed if u.token == "cheval_vapeur")
    tokens = {u.token for u in find_dependents(cheval_vapeur, seed)}
    assert "CV" in tokens


def test_find_dependents_is_empty_for_lookup_only_units(seed):
    galette = next(u for u in seed if u.token == "galette")
    assert find_dependents(galette, seed) == []
```

`libs/unit-registry/tests/test_events.py`:

```python
from datetime import datetime

import pytest

from unit_registry.events import EVENT_CREATED, make_event, parse_event
from unit_registry.types import Unit


def test_event_round_trip():
    unit = Unit(id="u1", token="sac", dimension="mass")
    payload = make_event(EVENT_CREATED, 7, unit, datetime(2026, 10, 6, 12, 0, 0))
    assert payload["occurred_at"] == "2026-10-06T12:00:00Z"
    assert parse_event(payload) == (EVENT_CREATED, 7, unit)


@pytest.mark.parametrize("payload", [
    {},
    {"event": "unit.created"},
    {"event": "nope", "registry_version": 1, "unit": {"id": "u", "token": "t", "status": "ACTIVE", "source": "manual"}},
])
def test_malformed_events_raise_value_error(payload):
    with pytest.raises(ValueError):
        parse_event(payload)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `scripts/unit-registry-test.sh libs/unit-registry -q tests/test_guards.py tests/test_events.py`
Expected: FAIL with `ModuleNotFoundError` for `unit_registry.guards` / `unit_registry.events`.

- [ ] **Step 3: Write `events.py`**

`libs/unit-registry/src/unit_registry/events.py`:

```python
"""Outbox event payloads published on the normalization.units fanout (spec §5)."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping

from .types import Unit, unit_from_dict, unit_to_dict

EVENT_CREATED = "unit.created"
EVENT_UPDATED = "unit.updated"
EVENT_DISABLED = "unit.disabled"
_EVENTS = frozenset({EVENT_CREATED, EVENT_UPDATED, EVENT_DISABLED})


def make_event(event: str, registry_version: int, unit: Unit, occurred_at: datetime) -> dict[str, Any]:
    return {
        "event": event,
        "registry_version": registry_version,
        "unit_id": unit.id,
        "unit": unit_to_dict(unit),
        "occurred_at": occurred_at.isoformat() + "Z",
    }


def parse_event(payload: Mapping[str, Any]) -> tuple[str, int, Unit]:
    try:
        event = payload["event"]
        version = int(payload["registry_version"])
        unit = unit_from_dict(payload["unit"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"malformed unit event: {exc}") from exc
    if event not in _EVENTS:
        raise ValueError(f"unknown unit event {event!r}")
    return event, version, unit
```

- [ ] **Step 4: Write `guards.py`**

`libs/unit-registry/src/unit_registry/guards.py`:

```python
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
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `scripts/unit-registry-test.sh libs/unit-registry -q`
Expected: all tests pass. (`test_guards.py` builds several pint registries; allow ~30 s.)

- [ ] **Step 6: Commit**

```bash
git add libs/unit-registry/src/unit_registry/guards.py libs/unit-registry/src/unit_registry/events.py libs/unit-registry/tests/test_guards.py libs/unit-registry/tests/test_events.py
git commit -m "feat(unit-registry): G1-G6 guards, dependents check and event payloads" -m "EN: validate_unit() runs all six guards with forced pint evaluation (lazy-define trap), prefix-collision screening, a full-registry dry run of the mandatory sample and uniqueness of tokens and lookup keys." -m "FR : validate_unit() execute les six garde-fous avec evaluation pint forcee (piege du define paresseux), detection des collisions de prefixe, execution a blanc de l'echantillon obligatoire sur le registre complet et unicite des jetons et cles."
```

---

### Task 5: `unit_registry.proto` + proto codec

**Files:**
- Create: `protos/grpc_stubs/unit_registry.proto`
- Create: `libs/unit-registry/src/unit_registry/proto_codec.py`
- Create: `libs/unit-registry/tests/test_proto_codec.py`

**Interfaces:**
- Produces the gRPC service `unit_registry.UnitRegistryService` (13 RPCs), with Python modules `grpc_stubs.unit_registry_pb2` / `_pb2_grpc` and the Go package `unit_registry`.
- Produces `unit_registry.proto_codec`:
  - `sample_to_proto(RegressionSample) -> pb.RegressionSample`
  - `sample_from_proto(pb.RegressionSample) -> RegressionSample`
  - `unit_to_proto(Unit, *, registry_version=0, types=()) -> pb.UnitResponse`
  - `unit_from_proto(pb.UnitResponse) -> Unit`

- [ ] **Step 1: Write the failing test**

`libs/unit-registry/tests/test_proto_codec.py`:

```python
from datetime import datetime

from unit_registry.proto_codec import unit_from_proto, unit_to_proto
from unit_registry.types import RegressionSample, Unit, UnitSource, UnitStatus


def test_unit_proto_round_trip_keeps_every_field():
    unit = Unit(
        id="u1", token="sac", dimension="mass", pint_definition="sac_c = 25 * kilogram",
        aliases=("sacs",), depends_on=("kilogram",), status=UnitStatus.DISABLED,
        source=UnitSource.MANUAL, sort_order=300,
        regression_sample=RegressionSample(label="Poids", value="1", value_max="2",
                                           data_type="numeric_range", expected_canonical_value=25.0,
                                           expected_canonical_max=50.0, expected_canonical_unit="kilogram"),
        created_by="mcp:test", created_at=datetime(2026, 10, 6, 12, 0, 1),
        updated_at=datetime(2026, 10, 6, 12, 0, 2),
    )
    message = unit_to_proto(unit, registry_version=9, types=["CAPACITY"])
    assert message.registry_version == 9 and list(message.types) == ["CAPACITY"]
    assert unit_from_proto(message) == unit


def test_empty_optional_fields_map_to_none():
    message = unit_to_proto(Unit(id="u2", token="galette", dimension=None))
    back = unit_from_proto(message)
    assert back.dimension is None and back.pint_definition is None and back.regression_sample is None
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `scripts/unit-registry-test.sh libs/unit-registry -q tests/test_proto_codec.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'unit_registry.proto_codec'`.

- [ ] **Step 3: Write the proto**

`protos/grpc_stubs/unit_registry.proto`:

```proto
syntax = "proto3";

package unit_registry;

import "google/protobuf/field_mask.proto";

// Owned by unit-registry-service. Spec: docs/superpowers/specs/2026-10-06-unit-registry-combined-design.md
// Messages copied from the June design ([J] A.3) with the deltas noted inline.
service UnitRegistryService {
  // Units (WRITE = Bearer UNITS_ADMIN_KEY; READ and ValidateUnit = open)
  rpc RegisterUnit(RegisterUnitRequest) returns (UnitResponse);
  rpc GetUnit(GetUnitRequest) returns (UnitResponse);
  rpc ListUnits(ListUnitsRequest) returns (ListUnitsResponse);
  rpc UpdateUnit(UpdateUnitRequest) returns (UnitResponse);
  rpc DeleteUnit(DeleteUnitRequest) returns (DeleteUnitResponse);            // soft: status=DISABLED
  rpc GetRegistryStatus(GetRegistryStatusRequest) returns (RegistryStatus);
  rpc ValidateUnit(ValidateUnitRequest) returns (ValidationResult);          // read-only dry run

  // Unit types (C9) — metadata only, never propagated to the normalizer
  rpc CreateUnitType(CreateUnitTypeRequest) returns (UnitTypeResponse);
  rpc UpdateUnitType(UpdateUnitTypeRequest) returns (UnitTypeResponse);
  rpc DeactivateUnitType(DeactivateUnitTypeRequest) returns (UnitTypeResponse);
  rpc GetUnitType(GetUnitTypeRequest) returns (UnitTypeResponse);
  rpc ListUnitTypes(ListUnitTypesRequest) returns (ListUnitTypesResponse);
  rpc SetDimensionTypes(SetDimensionTypesRequest) returns (DimensionTypesResponse);
}

message RegressionSample {
  string label = 1;
  string unit = 2;                            // empty -> the unit's own token
  string value = 3;
  string data_type = 4;                       // "numeric" | "numeric_range"
  double expected_canonical_value = 5;
  optional double expected_canonical_max = 6; // numeric_range only
  string expected_canonical_unit = 7;
  optional string value_max = 8;              // numeric_range input max (plan delta P4)
}

message UnitSpec {
  string token = 1;
  bool case_sensitive = 2;                    // P2-only: must be false
  repeated string aliases = 3;
  string kind = 4;                            // P2-only: "" or "NORMAL"
  string label_condition = 5;                 // P2-only
  string pint_definition = 6;
  repeated string depends_on = 7;
  string rewrite_expression = 8;              // P2-only
  string dimension = 9;
  string canonical_override = 10;             // P2-only
  RegressionSample regression_sample = 11;
}

message UnitResponse {
  string id = 1;
  UnitSpec spec = 2;
  string status = 3;                          // ACTIVE | PENDING | REJECTED | DISABLED
  string source = 4;                          // seed | manual | auto_proposal
  string created_by = 5;
  string created_at = 6;
  string updated_at = 7;
  int64 registry_version = 8;
  repeated string types = 9;                  // active type codes inherited from the dimension (C9)
  int64 sort_order = 10;                      // define application order (plan delta P1)
}

message RegisterUnitRequest { UnitSpec spec = 1; string created_by = 2; }
message GetUnitRequest { string id = 1; string token = 2; }

message ListUnitsRequest {
  string status = 1;
  string dimension = 2;
  int32 limit = 3;                            // <= 0: every row (plan delta P8)
  int32 offset = 4;
  string type = 5;                            // unit-type code filter (C9)
}
message ListUnitsResponse { repeated UnitResponse units = 1; int64 total = 2; int64 registry_version = 3; }

message UpdateUnitRequest {
  string id = 1;
  UnitSpec spec = 2;
  google.protobuf.FieldMask update_mask = 3;  // dimension, pint_definition, aliases, depends_on, regression_sample
  string updated_by = 4;
}

message DeleteUnitRequest { string id = 1; string deleted_by = 2; }
message DeleteUnitResponse { bool success = 1; }

message GetRegistryStatusRequest {}
message RegistryStatus { int64 loaded_version = 1; string last_reconcile_at = 2; int64 active_unit_count = 3; }

message ValidateUnitRequest { UnitSpec spec = 1; string id = 2; }  // id set -> validate as an update of that unit
message GuardResult { string guard = 1; bool ok = 2; bool skipped = 3; string message = 4; }
message DryRunResult {
  bool ok = 1;
  double canonical_value = 2;
  optional double canonical_max = 3;
  string canonical_unit = 4;
  bool bypassed = 5;
  string error = 6;
}
message ValidationResult { bool overall_ok = 1; repeated GuardResult guards = 2; DryRunResult dry_run = 3; }

message UnitTypeSpec { string code = 1; string label = 2; string description = 3; }
message UnitTypeResponse {
  string id = 1;
  UnitTypeSpec spec = 2;
  bool is_active = 3;
  repeated string dimensions = 4;
  string created_by = 5;
  string created_at = 6;
  string updated_at = 7;
}
message CreateUnitTypeRequest { UnitTypeSpec spec = 1; string created_by = 2; }
message UpdateUnitTypeRequest { string id = 1; UnitTypeSpec spec = 2; google.protobuf.FieldMask update_mask = 3; string updated_by = 4; }
message DeactivateUnitTypeRequest { string id = 1; string updated_by = 2; }
message GetUnitTypeRequest { string id = 1; string code = 2; }
message ListUnitTypesRequest { bool include_inactive = 1; }
message ListUnitTypesResponse { repeated UnitTypeResponse types = 1; }
message SetDimensionTypesRequest { string dimension = 1; repeated string type_codes = 2; string updated_by = 3; }
message DimensionTypesResponse { string dimension = 1; repeated string type_codes = 2; }
```

- [ ] **Step 4: Write the codec**

`libs/unit-registry/src/unit_registry/proto_codec.py`:

```python
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
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `scripts/unit-registry-test.sh libs/unit-registry -q`
Expected: all tests pass. The script regenerates stubs, so a proto syntax error shows up as a protoc error here.

- [ ] **Step 6: Commit**

```bash
git add protos/grpc_stubs/unit_registry.proto libs/unit-registry/src/unit_registry/proto_codec.py libs/unit-registry/tests/test_proto_codec.py
git commit -m "feat(protos): unit_registry.proto with unit and unit-type RPCs" -m "EN: New UnitRegistryService contract (June's unit messages + unit types C9 + plan deltas: sort_order, value_max, deleted_by, limit<=0 = all). graph_normalization.proto is untouched. Adds the Python Unit<->proto codec." -m "FR : Nouveau contrat UnitRegistryService (messages d'unite de juin + types d'unite C9 + ecarts du plan : sort_order, value_max, deleted_by, limit<=0 = tout). graph_normalization.proto n'est pas modifie. Ajoute le codec Python Unit<->proto."
```

---

### Task 6: `unit-registry-service` — DB models, repositories, bootstrap

**Files:**
- Create: `apps-microservices/unit-registry-service/requirements.txt`
- Create (under `apps-microservices/unit-registry-service/`): `app/__init__.py` (empty), `application/__init__.py` (empty), `application/clock.py`, `application/models.py`, `infrastructure/__init__.py` (empty), `infrastructure/db/__init__.py` (empty), `infrastructure/db/models.py`, `infrastructure/db/repository.py`, `infrastructure/db/bootstrap.py`
- Create: `tests/__init__.py` (empty), `tests/conftest.py`, `tests/test_repository.py`, `tests/test_mysql.py`

**Interfaces:**
- Consumes: `unit_registry.types`, `unit_registry.seed.build_seed_units`, `SEED_ACTOR`, `unit_registry.legacy.CANONICAL_UNITS`.
- Produces:
  - `application.clock.utcnow() -> datetime` (naive UTC, microsecond=0)
  - `application.models.UnitType(id, code, label, description, is_active, dimensions=(), created_by="", created_at=None, updated_at=None)`
  - `infrastructure.db.models.Base` plus row classes
  - `infrastructure.db.repository.UnitRepository(session)` with methods `lock_registry() -> int`, `current_version() -> int`, `bump_version(actor, now) -> int`, `dimension_ids() -> dict[name, id]`, `list_units(status=None, dimensions=None) -> list[Unit]`, `get_unit(id) -> Unit|None`, `get_unit_by_token(token) -> Unit|None`, `insert_unit(unit)`, `update_unit(unit)`, `max_sort_order() -> int`, `insert_event(version, payload, now)`, `active_count() -> int`
  - `TypeRepository(session)` with methods `list_types(include_inactive=False)`, `get_type(id)`, `get_type_by_code(code)`, `insert_type(t)`, `save_type(t)`, `types_by_dimension() -> dict[dim_name, list[code]]` (active types only), `set_dimension_types(dimension_id, type_ids, actor, now)`
  - `infrastructure.db.bootstrap.bootstrap(session, now)`, which is idempotent
  - pytest fixtures `engine`, `session_factory`, `seeded`, and the constant `NOW` in `tests/conftest.py`

- [ ] **Step 1: Write the failing tests**

`apps-microservices/unit-registry-service/tests/conftest.py`:

```python
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from infrastructure.db.bootstrap import bootstrap
from infrastructure.db.models import Base

NOW = datetime(2026, 10, 6, 12, 0, 0)


@pytest.fixture
def engine():
    eng = create_engine("sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    return eng


@pytest.fixture
def session_factory(engine):
    return sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
def seeded(session_factory):
    with session_factory.begin() as session:
        bootstrap(session, NOW)
    return session_factory
```

`apps-microservices/unit-registry-service/tests/test_repository.py`:

```python
from sqlalchemy import func, select

from infrastructure.db.bootstrap import bootstrap
from infrastructure.db.models import UnitDimensionRow, UnitEventRow, UnitRow, UnitTypeRow
from infrastructure.db.repository import TypeRepository, UnitRepository
from unit_registry.legacy import CANONICAL_UNITS
from unit_registry.seed import build_seed_units
from unit_registry.types import UnitStatus

from .conftest import NOW


def count(session, row):
    return session.scalar(select(func.count()).select_from(row))


def test_bootstrap_seeds_dimensions_units_types_and_version(seeded):
    with seeded() as s:
        assert count(s, UnitDimensionRow) == len(CANONICAL_UNITS)
        assert count(s, UnitRow) == len(build_seed_units())
        assert {t.code for t in TypeRepository(s).list_types()} == {"DIMENSION", "CAPACITY"}
        assert UnitRepository(s).current_version() == 1
        assert count(s, UnitEventRow) == 0


def test_bootstrap_is_idempotent(seeded):
    with seeded.begin() as s:
        bootstrap(s, NOW)
    with seeded() as s:
        assert count(s, UnitRow) == len(build_seed_units())
        assert count(s, UnitTypeRow) == 2


def test_units_round_trip_through_the_database(seeded):
    expected = {(u.token, u.pint_definition, u.dimension, u.sort_order) for u in build_seed_units()}
    with seeded() as s:
        got = {(u.token, u.pint_definition, u.dimension, u.sort_order)
               for u in UnitRepository(s).list_units(status=UnitStatus.ACTIVE)}
    assert got == expected


def test_token_lookup_is_exact(seeded):
    with seeded() as s:
        repo = UnitRepository(s)
        assert repo.get_unit_by_token("Litres").token == "Litres"
        assert repo.get_unit_by_token("litres").token == "litres"
        assert repo.get_unit_by_token("LITRES") is None


def test_bump_version_increments(seeded):
    with seeded.begin() as s:
        assert UnitRepository(s).bump_version("tester", NOW) == 2
    with seeded() as s:
        assert UnitRepository(s).current_version() == 2


def test_dimension_filter(seeded):
    with seeded() as s:
        units = UnitRepository(s).list_units(dimensions={"length"})
    assert units and all(u.dimension == "length" for u in units)
```

`apps-microservices/unit-registry-service/tests/test_mysql.py`:

```python
"""Runs only against a real MySQL 8 (Review Focus 1). See Task 6 Step 6 for the command."""
import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from infrastructure.db.bootstrap import bootstrap
from infrastructure.db.models import Base
from infrastructure.db.repository import UnitRepository
from unit_registry.types import Unit

from .conftest import NOW

MYSQL_URL = os.environ.get("MYSQL_TEST_URL")
pytestmark = pytest.mark.skipif(not MYSQL_URL, reason="MYSQL_TEST_URL not set")


@pytest.fixture
def mysql_factory():
    engine = create_engine(MYSQL_URL)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory.begin() as s:
        bootstrap(s, NOW)
    yield factory
    Base.metadata.drop_all(engine)


def test_mysql_collation_keeps_tokens_distinct(mysql_factory):
    with mysql_factory() as s:
        repo = UnitRepository(s)
        assert repo.get_unit_by_token("Litres").token == "Litres"
        assert repo.get_unit_by_token("litres").token == "litres"
        assert repo.get_unit_by_token("décibels").token == "décibels"
        assert repo.get_unit_by_token("decibels").token == "decibels"


def test_mysql_rejects_an_exact_duplicate_token(mysql_factory):
    with pytest.raises(IntegrityError):
        with mysql_factory.begin() as s:
            UnitRepository(s).insert_unit(Unit(id="dup", token="kg", dimension="mass",
                                               created_at=NOW, updated_at=NOW))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `scripts/unit-registry-test.sh apps-microservices/unit-registry-service -q`
Expected: collection error `ModuleNotFoundError: No module named 'infrastructure'`.

- [ ] **Step 3: Write requirements, clock and app models**

`apps-microservices/unit-registry-service/requirements.txt`:

```text
grpcio==1.68.1
grpcio-tools==1.68.1
protobuf>=5.26.1,<6
pydantic>=2
pydantic-settings>=2
SQLAlchemy==2.0.36
PyMySQL==1.1.1
cryptography
pika==1.3.2
prometheus-client
pint==0.24.4
```

`application/clock.py`:

```python
from datetime import datetime, timezone


def utcnow() -> datetime:
    """Naive UTC, second precision: round-trips exactly through MySQL DATETIME."""
    return datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
```

`application/models.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class UnitType:
    """Business category of measurement (spec §4.4, C9). Metadata only."""

    id: str
    code: str
    label: str
    description: str | None
    is_active: bool
    dimensions: tuple[str, ...] = ()
    created_by: str = ""
    created_at: datetime | None = None
    updated_at: datetime | None = None
```

- [ ] **Step 4: Write the SQLAlchemy models**

`infrastructure/db/models.py`:

```python
"""normalization_db schema (spec §4 / [J] §4, plus plan deltas P1-P2 and C9 tables)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CHAR,
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _bin(length: int):
    """Accent- and case-sensitive VARCHAR on MySQL ('décibels' != 'decibels', 'Litres' != 'litres')."""
    return String(length).with_variant(
        mysql.VARCHAR(length, charset="utf8mb4", collation="utf8mb4_bin"), "mysql"
    )


# SQLite only auto-increments an INTEGER PRIMARY KEY.
_BIGINT_PK = BigInteger().with_variant(Integer, "sqlite")
_MYSQL = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"}
_SOURCE = Enum("seed", "manual", "auto_proposal", name="unit_source")


class Base(DeclarativeBase):
    pass


class UnitDimensionRow(Base):
    __tablename__ = "unit_dimensions"
    __table_args__ = (UniqueConstraint("name", name="uniq_dim_name"), _MYSQL)

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True)
    name: Mapped[str] = mapped_column(_bin(64))
    canonical_unit: Mapped[str] = mapped_column(String(128))
    bypass_pint: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime)


class UnitRow(Base):
    __tablename__ = "units"
    __table_args__ = (
        UniqueConstraint("token", name="uniq_unit_token"),
        Index("idx_unit_status", "status"),
        Index("idx_unit_dimension", "dimension_id"),
        Index("idx_unit_kind", "kind"),
        {**_MYSQL, "mysql_collate": "utf8mb4_bin"},
    )

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True)
    token: Mapped[str] = mapped_column(_bin(128))
    case_sensitive: Mapped[bool] = mapped_column(Boolean, default=False)
    aliases: Mapped[list | None] = mapped_column(JSON, nullable=True)
    kind: Mapped[str] = mapped_column(Enum("NORMAL", "PASSTHROUGH", name="unit_kind"), default="NORMAL")
    label_condition: Mapped[str | None] = mapped_column(String(128), nullable=True)
    pint_definition: Mapped[str | None] = mapped_column(_bin(255), nullable=True)
    depends_on: Mapped[list | None] = mapped_column(JSON, nullable=True)
    rewrite_expression: Mapped[str | None] = mapped_column(String(255), nullable=True)
    dimension_id: Mapped[str | None] = mapped_column(
        CHAR(36), ForeignKey("unit_dimensions.id", ondelete="RESTRICT"), nullable=True
    )
    canonical_override: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(
        Enum("ACTIVE", "PENDING", "REJECTED", "DISABLED", name="unit_status"), default="ACTIVE"
    )
    source: Mapped[str] = mapped_column(_SOURCE, default="manual")
    regression_sample: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # plan delta P2
    sort_order: Mapped[int] = mapped_column(BigInteger, default=0)  # plan delta P1
    created_by: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime)


class RegistryMetaRow(Base):
    __tablename__ = "registry_meta"
    __table_args__ = (CheckConstraint("id = 1", name="chk_meta_singleton"), _MYSQL)

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=False)
    registry_version: Mapped[int] = mapped_column(BigInteger, default=1)
    last_bumped_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_bumped_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class UnitEventRow(Base):
    """Transactional outbox (spec §4.1)."""

    __tablename__ = "unit_events"
    __table_args__ = (UniqueConstraint("registry_version", name="uniq_event_version"), _MYSQL)

    id: Mapped[int] = mapped_column(_BIGINT_PK, primary_key=True, autoincrement=True)
    registry_version: Mapped[int] = mapped_column(BigInteger)
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class UnitTypeRow(Base):
    __tablename__ = "unit_types"
    __table_args__ = (UniqueConstraint("code", name="uniq_unit_type_code"), _MYSQL)

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True)
    code: Mapped[str] = mapped_column(String(64))
    label: Mapped[str] = mapped_column(String(128))
    description: Mapped[str | None] = mapped_column(String(512), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime)


class DimensionUnitTypeRow(Base):
    __tablename__ = "dimension_unit_types"
    __table_args__ = (_MYSQL,)

    dimension_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("unit_dimensions.id", ondelete="RESTRICT"), primary_key=True
    )
    unit_type_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("unit_types.id", ondelete="RESTRICT"), primary_key=True
    )
    created_by: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime)


# --- Created in P1, used from P2/P3 (spec §4.2): schema only, never read in P1. ---


class LabelRuleRow(Base):
    __tablename__ = "label_rules"
    __table_args__ = (
        UniqueConstraint("key_substring", name="uniq_label_key"),
        UniqueConstraint("priority", name="uniq_label_priority"),
        Index("idx_label_active_priority", "is_active", "priority"),
        {**_MYSQL, "mysql_collate": "utf8mb4_bin"},
    )

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True)
    key_substring: Mapped[str] = mapped_column(_bin(255))
    dimension_id: Mapped[str] = mapped_column(CHAR(36), ForeignKey("unit_dimensions.id", ondelete="RESTRICT"))
    priority: Mapped[int] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    source: Mapped[str] = mapped_column(_SOURCE, default="manual")
    created_by: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime)


class DisambiguationRuleRow(Base):
    __tablename__ = "disambiguation_rules"
    __table_args__ = (
        UniqueConstraint("trigger_unit", name="uniq_disambig_trigger"),
        {**_MYSQL, "mysql_collate": "utf8mb4_bin"},
    )

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True)
    trigger_unit: Mapped[str] = mapped_column(_bin(128))
    keyword_list: Mapped[list] = mapped_column(JSON)
    match_dimension_id: Mapped[str] = mapped_column(CHAR(36), ForeignKey("unit_dimensions.id", ondelete="RESTRICT"))
    match_pint_expr: Mapped[str | None] = mapped_column(String(255), nullable=True)
    default_dimension_id: Mapped[str | None] = mapped_column(
        CHAR(36), ForeignKey("unit_dimensions.id", ondelete="RESTRICT"), nullable=True
    )
    default_pint_expr: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime)


class UnitProposalRow(Base):
    __tablename__ = "unit_proposals"
    __table_args__ = (
        UniqueConstraint("dedup_key", name="uniq_proposal_dedup"),
        Index("idx_proposal_state_occ", "state", "occurrence_count"),
        _MYSQL,
    )

    id: Mapped[int] = mapped_column(_BIGINT_PK, primary_key=True, autoincrement=True)
    dedup_key: Mapped[str] = mapped_column(CHAR(64))
    raw_unit: Mapped[str] = mapped_column(String(128))
    normalized_unit: Mapped[str] = mapped_column(String(128))
    dimension_hint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    data_type: Mapped[str] = mapped_column(String(32))
    occurrence_count: Mapped[int] = mapped_column(BigInteger, default=1)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime)
    sample_labels: Mapped[list] = mapped_column(JSON)
    sample_value: Mapped[str | None] = mapped_column(String(64), nullable=True)
    state: Mapped[str] = mapped_column(
        Enum("PENDING", "VALIDATING", "ACTIVE", "REJECTED", "REJECTED_VALIDATION", "SUPERSEDED",
             name="proposal_state"),
        default="PENDING",
    )
    proposed_definition: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_by: Mapped[str] = mapped_column(String(64), default="auto-collector")
    reviewed_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime)
```

- [ ] **Step 5: Write the repositories and bootstrap**

`infrastructure/db/repository.py`:

```python
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
```

`infrastructure/db/bootstrap.py`:

```python
"""Idempotent first-boot data ([J] §9.1 "skip if exists")."""
from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from application.models import UnitType
from unit_registry.legacy import CANONICAL_UNITS
from unit_registry.seed import SEED_ACTOR, build_seed_units

from .models import RegistryMetaRow, UnitDimensionRow, UnitRow, UnitTypeRow
from .repository import TypeRepository, UnitRepository

BYPASS_DIMENSIONS = frozenset({"count", "count_rate"})
SEED_TYPES = (("DIMENSION", "Dimension"), ("CAPACITY", "Capacité"))  # no links: operator decision (§4.4)
_NAMESPACE = uuid.UUID("0b8f3d7a-52e1-4c8e-9a3f-7d61c2e4b915")


def _seed_id(kind: str, key: str) -> str:
    return str(uuid.uuid5(_NAMESPACE, f"{kind}:{key}"))


def _empty(session: Session, row) -> bool:
    return not session.scalar(select(func.count()).select_from(row))


def bootstrap(session: Session, now: datetime) -> None:
    if session.get(RegistryMetaRow, 1) is None:
        session.add(RegistryMetaRow(id=1, registry_version=1))
    if _empty(session, UnitDimensionRow):
        for name, canonical in CANONICAL_UNITS.items():
            session.add(UnitDimensionRow(
                id=_seed_id("dimension", name), name=name, canonical_unit=canonical,
                bypass_pint=name in BYPASS_DIMENSIONS, is_active=True,
                created_by=SEED_ACTOR, created_at=now, updated_at=now,
            ))
        session.flush()
    if _empty(session, UnitRow):
        repo = UnitRepository(session)
        for unit in build_seed_units():
            repo.insert_unit(replace(unit, created_at=now, updated_at=now))
    if _empty(session, UnitTypeRow):
        types = TypeRepository(session)
        for code, label in SEED_TYPES:
            types.insert_type(UnitType(id=_seed_id("type", code), code=code, label=label,
                                       description=None, is_active=True, created_by=SEED_ACTOR,
                                       created_at=now, updated_at=now))
    session.flush()
```

- [ ] **Step 6: Run the tests**

Run: `scripts/unit-registry-test.sh apps-microservices/unit-registry-service -q`
Expected: the 6 repository tests pass. The 2 MySQL tests are skipped (`MYSQL_TEST_URL not set`).

Then run the MySQL tests against a throwaway MySQL 8 (Review Focus 1):

```bash
docker network create unit-registry-test-net 2>/dev/null || true
docker run -d --name unit-registry-mysql --network unit-registry-test-net \
  -e MYSQL_ROOT_PASSWORD=test -e MYSQL_DATABASE=normalization_db mysql:8.0
docker network connect unit-registry-test-net unit-registry-test 2>/dev/null || true
until docker exec unit-registry-mysql mysqladmin ping -uroot -ptest --silent; do sleep 2; done
docker exec -w /repo/apps-microservices/unit-registry-service \
  -e MYSQL_TEST_URL='mysql+pymysql://root:test@unit-registry-mysql:3306/normalization_db?charset=utf8mb4' \
  unit-registry-test python -m pytest -q tests/test_mysql.py
```

Expected: `2 passed`. Keep `unit-registry-mysql` running for Task 16; it's removed at the end of the plan.

- [ ] **Step 7: Commit**

```bash
git add apps-microservices/unit-registry-service
git commit -m "feat(unit-registry-service): normalization_db schema, repositories and idempotent bootstrap" -m "EN: SQLAlchemy models for June's tables plus the outbox and unit types; binary collation keeps Litres/litres and décibels/decibels distinct (MySQL test). Bootstrap seeds dimensions, the 233 seed units and the DIMENSION/CAPACITY types." -m "FR : Modeles SQLAlchemy des tables de juin plus l'outbox et les types d'unite ; la collation binaire garde Litres/litres et décibels/decibels distincts (test MySQL). Le bootstrap seme les dimensions, les 233 unites du seed et les types DIMENSION/CAPACITY."
```

---

### Task 7: `UnitService` — register / update / disable / get / list / validate

**Files:**
- Create: `apps-microservices/unit-registry-service/application/errors.py`, `application/unit_service.py`
- Create: `apps-microservices/unit-registry-service/tests/test_unit_service.py`

**Interfaces:**
- Consumes: `UnitRepository`, `TypeRepository`, `unit_registry.guards.validate_unit`, `find_dependents`, `unit_registry.events.*`, `application.clock.utcnow`.
- Produces:
  - `application.errors`: `ServiceError` (base, attribute `code`), `NotFound` ("NOT_FOUND"), `AlreadyExists` ("ALREADY_EXISTS"), `InvalidArgument` ("INVALID_ARGUMENT"), `FailedPrecondition` ("FAILED_PRECONDITION")
  - `application.unit_service.UnitDraft(token, dimension, pint_definition=None, aliases=(), depends_on=(), regression_sample=None)`
  - `UPDATABLE_FIELDS = {"dimension", "pint_definition", "aliases", "depends_on", "regression_sample"}`
  - `UnitService(session_factory, clock=utcnow, new_id=uuid4-str)` with methods:
    - `register(draft, actor) -> tuple[Unit, int]`
    - `update(unit_id, changes, actor) -> tuple[Unit, int]`
    - `disable(unit_id, actor) -> tuple[Unit, int]`
    - `get(*, unit_id=None, token=None) -> Unit`
    - `list(*, status=None, dimension=None, type_code=None) -> tuple[list[Unit], int]`
    - `validate(draft, *, unit_id=None) -> ValidationOutcome`
    - `registry_status() -> tuple[int, int]`
    - `types_for(units) -> dict[unit_id, list[str]]`

- [ ] **Step 1: Write the failing tests**

`apps-microservices/unit-registry-service/tests/test_unit_service.py`:

```python
import pytest
from sqlalchemy import select

from application.errors import AlreadyExists, FailedPrecondition, InvalidArgument, NotFound
from application.unit_service import UnitDraft, UnitService
from infrastructure.db.models import UnitEventRow
from unit_registry.types import RegressionSample, UnitStatus

from .conftest import NOW


def sample(expected=50.0, value="2"):
    return RegressionSample(label="Poids", value=value, expected_canonical_value=expected,
                            expected_canonical_unit="kilogram")


def draft(**overrides) -> UnitDraft:
    base = dict(token="sac_ciment", dimension="mass", pint_definition="sac_ciment = 25 * kilogram",
                regression_sample=sample())
    base.update(overrides)
    return UnitDraft(**base)


@pytest.fixture
def service(seeded):
    ids = iter(f"id-{n}" for n in range(1000))
    return UnitService(seeded, clock=lambda: NOW, new_id=lambda: next(ids))


def events(seeded):
    with seeded() as s:
        return [(r.registry_version, r.payload["event"], r.payload["unit"]["token"])
                for r in s.execute(select(UnitEventRow).order_by(UnitEventRow.registry_version)).scalars()]


def test_register_commits_row_version_and_outbox_event(service, seeded):
    unit, version = service.register(draft(), "tester")
    assert version == 2 and unit.status is UnitStatus.ACTIVE and unit.created_by == "tester"
    assert events(seeded) == [(2, "unit.created", "sac_ciment")]
    assert service.get(token="sac_ciment").id == unit.id


def test_register_without_sample_is_invalid(service):
    with pytest.raises(InvalidArgument, match="G4"):
        service.register(draft(regression_sample=None), "tester")


def test_register_without_dimension_is_invalid(service):
    with pytest.raises(InvalidArgument, match="dimension"):
        service.register(draft(dimension=None), "tester")


def test_register_an_existing_token_already_exists(service):
    with pytest.raises(AlreadyExists, match="kg"):
        service.register(draft(token="kg", pint_definition=None), "tester")


def test_register_lazy_bad_define_fails_g1(service, seeded):
    with pytest.raises(InvalidArgument, match="G1"):
        service.register(draft(token="baz_x", pint_definition="baz_x = 3 * nonexistent_y"), "tester")
    assert events(seeded) == []


def test_register_alias_clash_already_exists(service):
    with pytest.raises(AlreadyExists, match="G6"):
        service.register(draft(aliases=("kg",)), "tester")


def test_update_revalidates_and_emits_an_event(service, seeded):
    unit, _ = service.register(draft(), "tester")
    updated, version = service.update(
        unit.id, {"pint_definition": "sac_ciment = 20 * kilogram", "regression_sample": sample(40.0)}, "editor")
    assert version == 3 and updated.pint_definition == "sac_ciment = 20 * kilogram"
    assert events(seeded)[-1] == (3, "unit.updated", "sac_ciment")


def test_update_of_a_seed_unit_needs_a_sample(service):
    kg = service.get(token="kg")
    with pytest.raises(InvalidArgument, match="G4"):
        service.update(kg.id, {"aliases": ("kilo",)}, "editor")


def test_update_rejects_unknown_fields(service):
    kg = service.get(token="kg")
    with pytest.raises(InvalidArgument, match="token"):
        service.update(kg.id, {"token": "kgs"}, "editor")


def test_update_unknown_unit_is_not_found(service):
    with pytest.raises(NotFound):
        service.update("missing", {"aliases": ()}, "editor")


def test_disable_is_idempotent(service, seeded):
    unit, _ = service.register(draft(), "tester")
    disabled, version = service.disable(unit.id, "editor")
    assert disabled.status is UnitStatus.DISABLED and version == 3
    again, version_again = service.disable(unit.id, "editor")
    assert again.status is UnitStatus.DISABLED and version_again == 3
    assert [e[1] for e in events(seeded)] == ["unit.created", "unit.disabled"]


def test_disable_refuses_when_other_units_depend_on_it(service):
    cheval_vapeur = service.get(token="cheval_vapeur")
    with pytest.raises(FailedPrecondition, match="CV"):
        service.disable(cheval_vapeur.id, "editor")


def test_register_reactivates_a_disabled_token(service, seeded):
    unit, _ = service.register(draft(), "tester")
    service.disable(unit.id, "editor")
    revived, version = service.register(draft(), "tester")
    assert revived.id == unit.id and revived.status is UnitStatus.ACTIVE and version == 4
    assert events(seeded)[-1] == (4, "unit.created", "sac_ciment")


def test_validate_is_read_only(service, seeded):
    outcome = service.validate(draft())
    assert outcome.ok
    assert service.registry_status()[0] == 1 and events(seeded) == []


def test_list_filters_and_reports_the_version(service):
    units, version = service.list(status=UnitStatus.ACTIVE, dimension="length")
    assert version == 1 and units and all(u.dimension == "length" for u in units)


def test_get_requires_id_or_token(service):
    with pytest.raises(InvalidArgument):
        service.get()
    with pytest.raises(NotFound):
        service.get(token="nope")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `scripts/unit-registry-test.sh apps-microservices/unit-registry-service -q tests/test_unit_service.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'application.errors'`.

- [ ] **Step 3: Write `errors.py`**

`application/errors.py`:

```python
class ServiceError(Exception):
    code = "INTERNAL"


class NotFound(ServiceError):
    code = "NOT_FOUND"


class AlreadyExists(ServiceError):
    code = "ALREADY_EXISTS"


class InvalidArgument(ServiceError):
    code = "INVALID_ARGUMENT"


class FailedPrecondition(ServiceError):
    code = "FAILED_PRECONDITION"
```

- [ ] **Step 4: Write `unit_service.py`**

`application/unit_service.py`:

```python
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
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `scripts/unit-registry-test.sh apps-microservices/unit-registry-service -q`
Expected: all tests pass (repository + unit service; MySQL skipped).

- [ ] **Step 6: Commit**

```bash
git add apps-microservices/unit-registry-service/application apps-microservices/unit-registry-service/tests/test_unit_service.py
git commit -m "feat(unit-registry-service): unit use cases with guarded writes and transactional outbox" -m "EN: register/update/disable lock registry_meta, run G1-G6 against the full active registry, then write row + version bump + outbox event in one transaction. Disabling a unit others depend on is refused; re-creating a disabled token reactivates it." -m "FR : register/update/disable verrouillent registry_meta, executent G1-G6 sur le registre actif complet, puis ecrivent ligne + increment de version + evenement outbox dans une transaction. Desactiver une unite dont d'autres dependent est refuse ; recreer un jeton desactive le reactive."
```

---

### Task 8: `TypeService` — unit types (C9)

**Files:**
- Create: `apps-microservices/unit-registry-service/application/types_service.py`
- Create: `apps-microservices/unit-registry-service/tests/test_types_service.py`

**Interfaces:**
- Consumes: `TypeRepository`, `UnitRepository.dimension_ids()`, `application.errors.*`, `application.models.UnitType`.
- Produces:
  - `application.types_service.CODE_PATTERN`
  - `fold_code(code) -> str`
  - `TypeService(session_factory, clock=utcnow, new_id=uuid4-str)` with methods:
    - `create(code, label, description, actor) -> UnitType`
    - `update(type_id, changes, actor) -> UnitType`
    - `deactivate(type_id, actor) -> UnitType`
    - `get(*, type_id=None, code=None) -> UnitType`
    - `list(include_inactive=False) -> list[UnitType]`
    - `set_dimension_types(dimension, codes, actor) -> list[str]`

- [ ] **Step 1: Write the failing tests**

`apps-microservices/unit-registry-service/tests/test_types_service.py`:

```python
import pytest
from sqlalchemy import func, select

from application.errors import AlreadyExists, FailedPrecondition, InvalidArgument, NotFound
from application.types_service import TypeService
from application.unit_service import UnitService
from infrastructure.db.models import UnitEventRow
from unit_registry.types import UnitStatus

from .conftest import NOW


@pytest.fixture
def types(seeded):
    ids = iter(f"t-{n}" for n in range(1000))
    return TypeService(seeded, clock=lambda: NOW, new_id=lambda: next(ids))


@pytest.fixture
def units(seeded):
    return UnitService(seeded, clock=lambda: NOW)


def test_seed_types_exist_without_links(types):
    assert {(t.code, t.dimensions) for t in types.list()} == {("DIMENSION", ()), ("CAPACITY", ())}


def test_create_type(types):
    created = types.create("POIDS", "Poids", "Masse d'un objet", "tester")
    assert created.code == "POIDS" and created.is_active and types.get(code="POIDS").id == created.id


@pytest.mark.parametrize("code", ["capacity", "X", "CAPACITÉ", "1ABC", "A-B"])
def test_create_rejects_bad_codes(types, code):
    with pytest.raises(InvalidArgument):
        types.create(code, "label", None, "tester")


def test_create_rejects_near_duplicates(types):
    with pytest.raises(AlreadyExists, match="CAPACITY"):
        types.create("CAPA_CITY", "Capacité", None, "tester")


def test_create_rejects_an_active_duplicate(types):
    with pytest.raises(AlreadyExists):
        types.create("CAPACITY", "Capacité", None, "tester")


def test_update_label_but_never_code(types):
    capacity = types.get(code="CAPACITY")
    assert types.update(capacity.id, {"label": "Contenance"}, "editor").label == "Contenance"
    with pytest.raises(InvalidArgument, match="immutable"):
        types.update(capacity.id, {"code": "VOLUME"}, "editor")


def test_deactivate_hides_but_keeps_links_and_create_reactivates(types, units):
    types.set_dimension_types("volume", ["CAPACITY"], "editor")
    capacity = types.get(code="CAPACITY")
    types.deactivate(capacity.id, "editor")
    litre = units.get(token="l")
    assert units.types_for([litre])[litre.id] == []
    assert [t.code for t in types.list()] == ["DIMENSION"]
    assert types.get(code="CAPACITY").dimensions == ("volume",)
    revived = types.create("CAPACITY", "Capacité", None, "editor")
    assert revived.is_active and units.types_for([litre])[litre.id] == ["CAPACITY"]


def test_set_dimension_types_replaces_and_is_idempotent(types, units):
    assert types.set_dimension_types("length", ["DIMENSION"], "editor") == ["DIMENSION"]
    assert types.set_dimension_types("length", ["DIMENSION", "DIMENSION"], "editor") == ["DIMENSION"]
    mm = units.get(token="mm")
    assert units.types_for([mm])[mm.id] == ["DIMENSION"]
    found, _ = units.list(status=UnitStatus.ACTIVE, type_code="DIMENSION")
    assert found and all(u.dimension == "length" for u in found)
    assert types.set_dimension_types("length", [], "editor") == []
    assert units.types_for([mm])[mm.id] == []


def test_set_dimension_types_rejects_unknown_and_inactive(types):
    with pytest.raises(NotFound, match="create_unit_type"):
        types.set_dimension_types("length", ["NOPE"], "editor")
    with pytest.raises(InvalidArgument, match="unknown dimension"):
        types.set_dimension_types("weight", ["DIMENSION"], "editor")
    types.deactivate(types.get(code="DIMENSION").id, "editor")
    with pytest.raises(FailedPrecondition):
        types.set_dimension_types("length", ["DIMENSION"], "editor")


def test_type_writes_never_touch_the_registry_version(types, units, seeded):
    types.create("POIDS", "Poids", None, "tester")
    types.set_dimension_types("mass", ["POIDS"], "tester")
    assert units.registry_status()[0] == 1
    with seeded() as s:
        assert s.scalar(select(func.count()).select_from(UnitEventRow)) == 0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `scripts/unit-registry-test.sh apps-microservices/unit-registry-service -q tests/test_types_service.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'application.types_service'`.

- [ ] **Step 3: Write `types_service.py`**

`application/types_service.py`:

```python
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `scripts/unit-registry-test.sh apps-microservices/unit-registry-service -q`
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/unit-registry-service/application/types_service.py apps-microservices/unit-registry-service/tests/test_types_service.py
git commit -m "feat(unit-registry-service): unit types linked to dimensions (C9)" -m "EN: Open vocabulary of unit types with explicit registration: bad or near-duplicate codes are rejected, codes are immutable, deactivation hides a type but keeps its links, and SetDimensionTypes replaces a dimension's set. Never bumps registry_version." -m "FR : Vocabulaire ouvert de types d'unite a enregistrement explicite : codes invalides ou quasi-doublons refuses, codes immuables, la desactivation masque un type sans perdre ses liens, et SetDimensionTypes remplace l'ensemble d'une dimension. N'incremente jamais registry_version."
```

---

### Task 9: gRPC servicer + admin-key interceptor

**Files:**
- Create: `apps-microservices/unit-registry-service/infrastructure/grpc/__init__.py` (empty), `auth.py`, `servicer.py`, `server.py`
- Create: `apps-microservices/unit-registry-service/tests/test_grpc.py`

**Interfaces:**
- Consumes: `UnitService`, `TypeService`, `UnitDraft`, `unit_registry.proto_codec`, `grpc_stubs.unit_registry_pb2(_grpc)`.
- Produces:
  - `infrastructure.grpc.auth.WRITE_METHODS`
  - `AdminKeyInterceptor(admin_key)`
  - `infrastructure.grpc.servicer.UnitRegistryServicer(units, types)`
  - `infrastructure.grpc.server.build_server(units, types, *, admin_key, port, max_workers=10) -> tuple[grpc.Server, int]` (the bound port)

- [ ] **Step 1: Write the failing tests**

`apps-microservices/unit-registry-service/tests/test_grpc.py`:

```python
import grpc
import pytest
from google.protobuf.field_mask_pb2 import FieldMask

from application.types_service import TypeService
from application.unit_service import UnitService
from grpc_stubs import unit_registry_pb2 as pb
from grpc_stubs import unit_registry_pb2_grpc as pb_grpc
from infrastructure.grpc.server import build_server

from .conftest import NOW

KEY = "test-admin-key-0123456789"
AUTH = (("authorization", f"Bearer {KEY}"),)


@pytest.fixture
def stub(seeded):
    server, port = build_server(UnitService(seeded, clock=lambda: NOW), TypeService(seeded, clock=lambda: NOW),
                                admin_key=KEY, port=0)
    server.start()
    channel = grpc.insecure_channel(f"localhost:{port}")
    yield pb_grpc.UnitRegistryServiceStub(channel)
    channel.close()
    server.stop(None)


def sac_spec(**overrides):
    spec = pb.UnitSpec(token="sac_ciment", dimension="mass", pint_definition="sac_ciment = 25 * kilogram",
                       regression_sample=pb.RegressionSample(label="Poids", value="2",
                                                             expected_canonical_value=50.0,
                                                             expected_canonical_unit="kilogram"))
    for key, value in overrides.items():
        setattr(spec, key, value)
    return spec


def code_of(call):
    with pytest.raises(grpc.RpcError) as info:
        call()
    return info.value.code(), info.value.details()


def test_writes_require_the_admin_bearer(stub):
    assert code_of(lambda: stub.RegisterUnit(pb.RegisterUnitRequest(spec=sac_spec())))[0] == grpc.StatusCode.UNAUTHENTICATED
    bad = (("authorization", "Bearer wrong"),)
    assert code_of(lambda: stub.RegisterUnit(pb.RegisterUnitRequest(spec=sac_spec()), metadata=bad))[0] == grpc.StatusCode.UNAUTHENTICATED


def test_reads_are_open(stub):
    assert stub.GetUnit(pb.GetUnitRequest(token="kg")).spec.dimension == "mass"


def test_register_get_update_delete_round_trip(stub):
    created = stub.RegisterUnit(pb.RegisterUnitRequest(spec=sac_spec(), created_by="mcp:test"), metadata=AUTH)
    assert created.registry_version == 2 and created.status == "ACTIVE" and created.created_by == "mcp:test"
    # The stored sample is re-run by G4, so an alias-only update needs no new sample.
    updated = stub.UpdateUnit(pb.UpdateUnitRequest(id=created.id, spec=pb.UnitSpec(aliases=["sacs"]),
                                                   update_mask=FieldMask(paths=["aliases"])), metadata=AUTH)
    assert list(updated.spec.aliases) == ["sacs"] and updated.registry_version == 3
    assert stub.DeleteUnit(pb.DeleteUnitRequest(id=created.id), metadata=AUTH).success
    assert stub.GetUnit(pb.GetUnitRequest(id=created.id)).status == "DISABLED"


def test_guard_failures_map_to_status_codes(stub):
    code, details = code_of(lambda: stub.RegisterUnit(
        pb.RegisterUnitRequest(spec=sac_spec(token="kg", pint_definition="")), metadata=AUTH))
    assert code == grpc.StatusCode.ALREADY_EXISTS and "kg" in details
    code, details = code_of(lambda: stub.RegisterUnit(pb.RegisterUnitRequest(
        spec=sac_spec(pint_definition="sac_ciment = 3 * nonexistent_y")), metadata=AUTH))
    assert code == grpc.StatusCode.INVALID_ARGUMENT and "G1" in details


def test_p2_only_fields_are_rejected(stub):
    code, details = code_of(lambda: stub.RegisterUnit(
        pb.RegisterUnitRequest(spec=sac_spec(kind="PASSTHROUGH")), metadata=AUTH))
    assert code == grpc.StatusCode.INVALID_ARGUMENT and "P2" in details
    code, _ = code_of(lambda: stub.RegisterUnit(
        pb.RegisterUnitRequest(spec=sac_spec(case_sensitive=True)), metadata=AUTH))
    assert code == grpc.StatusCode.INVALID_ARGUMENT


def test_update_mask_is_validated(stub):
    kg = stub.GetUnit(pb.GetUnitRequest(token="kg"))
    code, details = code_of(lambda: stub.UpdateUnit(
        pb.UpdateUnitRequest(id=kg.id, update_mask=FieldMask(paths=["token"])), metadata=AUTH))
    assert code == grpc.StatusCode.INVALID_ARGUMENT and "token" in details
    code, _ = code_of(lambda: stub.UpdateUnit(pb.UpdateUnitRequest(id=kg.id), metadata=AUTH))
    assert code == grpc.StatusCode.INVALID_ARGUMENT


def test_list_units_returns_everything_with_limit_zero_and_the_version(stub):
    response = stub.ListUnits(pb.ListUnitsRequest(status="ACTIVE", limit=0))
    assert response.total == len(response.units) > 200 and response.registry_version == 1
    page = stub.ListUnits(pb.ListUnitsRequest(status="ACTIVE", limit=10, offset=5))
    assert len(page.units) == 10 and page.total == response.total


def test_disable_with_dependents_is_failed_precondition(stub):
    cheval_vapeur = stub.GetUnit(pb.GetUnitRequest(token="cheval_vapeur"))
    code, details = code_of(lambda: stub.DeleteUnit(pb.DeleteUnitRequest(id=cheval_vapeur.id), metadata=AUTH))
    assert code == grpc.StatusCode.FAILED_PRECONDITION and "CV" in details


def test_validate_unit_is_open_and_reports_six_guards(stub):
    result = stub.ValidateUnit(pb.ValidateUnitRequest(spec=sac_spec()))
    assert result.overall_ok and [g.guard for g in result.guards] == ["G1", "G2", "G3", "G4", "G5", "G6"]
    assert result.dry_run.canonical_value == 50.0


def test_unit_type_rpcs_and_inherited_types(stub):
    created = stub.CreateUnitType(pb.CreateUnitTypeRequest(spec=pb.UnitTypeSpec(code="POIDS", label="Poids")),
                                  metadata=AUTH)
    assert created.is_active and created.spec.code == "POIDS"
    linked = stub.SetDimensionTypes(pb.SetDimensionTypesRequest(dimension="mass", type_codes=["POIDS"]),
                                    metadata=AUTH)
    assert list(linked.type_codes) == ["POIDS"]
    assert list(stub.GetUnit(pb.GetUnitRequest(token="kg")).types) == ["POIDS"]
    codes = [t.spec.code for t in stub.ListUnitTypes(pb.ListUnitTypesRequest()).types]
    assert codes == ["CAPACITY", "DIMENSION", "POIDS"]
    code, _ = code_of(lambda: stub.UpdateUnitType(
        pb.UpdateUnitTypeRequest(id=created.id, update_mask=FieldMask(paths=["code"])), metadata=AUTH))
    assert code == grpc.StatusCode.INVALID_ARGUMENT
    deactivated = stub.DeactivateUnitType(pb.DeactivateUnitTypeRequest(id=created.id), metadata=AUTH)
    assert not deactivated.is_active
    assert list(stub.GetUnitType(pb.GetUnitTypeRequest(code="POIDS")).dimensions) == ["mass"]
    code, _ = code_of(lambda: stub.SetDimensionTypes(
        pb.SetDimensionTypesRequest(dimension="mass", type_codes=["POIDS"]), metadata=AUTH))
    assert code == grpc.StatusCode.FAILED_PRECONDITION


def test_type_writes_require_the_bearer(stub):
    code, _ = code_of(lambda: stub.CreateUnitType(
        pb.CreateUnitTypeRequest(spec=pb.UnitTypeSpec(code="POIDS", label="Poids"))))
    assert code == grpc.StatusCode.UNAUTHENTICATED
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `scripts/unit-registry-test.sh apps-microservices/unit-registry-service -q tests/test_grpc.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'infrastructure.grpc'`.

- [ ] **Step 3: Write the interceptor**

`infrastructure/grpc/auth.py`:

```python
"""Bearer check on write RPCs ([J] D10 + B.3). Reads and ValidateUnit stay open.
The authorization header is never logged."""
from __future__ import annotations

import hmac

import grpc

_SERVICE = "/unit_registry.UnitRegistryService/"
WRITE_METHODS = frozenset(_SERVICE + name for name in (
    "RegisterUnit", "UpdateUnit", "DeleteUnit",
    "CreateUnitType", "UpdateUnitType", "DeactivateUnitType", "SetDimensionTypes",
))


class AdminKeyInterceptor(grpc.ServerInterceptor):
    def __init__(self, admin_key: str):
        if not admin_key:
            raise ValueError("UNITS_ADMIN_KEY must be set")
        self._expected = f"Bearer {admin_key}".encode()

        def deny(request, context):
            context.abort(grpc.StatusCode.UNAUTHENTICATED, "missing or invalid admin bearer")

        self._deny = grpc.unary_unary_rpc_method_handler(deny)

    def intercept_service(self, continuation, handler_call_details):
        if handler_call_details.method in WRITE_METHODS:
            metadata = dict(handler_call_details.invocation_metadata or ())
            supplied = metadata.get("authorization", "").encode()
            if not hmac.compare_digest(supplied, self._expected):
                return self._deny
        return continuation(handler_call_details)
```

- [ ] **Step 4: Write the servicer**

`infrastructure/grpc/servicer.py`:

```python
"""gRPC adapter: proto <-> application services; ServiceError -> status code."""
from __future__ import annotations

import functools
import logging

import grpc
from sqlalchemy.exc import SQLAlchemyError

from application.errors import InvalidArgument, ServiceError
from application.models import UnitType
from application.types_service import TypeService
from application.unit_service import UnitDraft, UnitService
from grpc_stubs import unit_registry_pb2 as pb
from grpc_stubs import unit_registry_pb2_grpc as pb_grpc
from unit_registry.guards import ValidationOutcome
from unit_registry.proto_codec import sample_from_proto, unit_to_proto
from unit_registry.types import Unit, UnitStatus

logger = logging.getLogger(__name__)

_STATUS = {
    "NOT_FOUND": grpc.StatusCode.NOT_FOUND,
    "ALREADY_EXISTS": grpc.StatusCode.ALREADY_EXISTS,
    "INVALID_ARGUMENT": grpc.StatusCode.INVALID_ARGUMENT,
    "FAILED_PRECONDITION": grpc.StatusCode.FAILED_PRECONDITION,
}
_P2_ONLY = ("label_condition", "rewrite_expression", "canonical_override")
_UNIT_PATHS = ("dimension", "pint_definition", "aliases", "depends_on", "regression_sample")
_TYPE_PATHS = ("label", "description")


def _rpc(method):
    @functools.wraps(method)
    def wrapper(self, request, context):
        try:
            return method(self, request, context)
        except ServiceError as exc:
            context.abort(_STATUS.get(exc.code, grpc.StatusCode.INTERNAL), str(exc))
        except SQLAlchemyError:
            logger.exception("database error in %s", method.__name__)
            context.abort(grpc.StatusCode.UNAVAILABLE, "unit registry database unavailable")
    return wrapper


def _reject_p2_fields(spec: pb.UnitSpec) -> None:
    used = [name for name in _P2_ONLY if getattr(spec, name)]
    if spec.kind not in ("", "NORMAL"):
        used.append("kind")
    if spec.case_sensitive:
        used.append("case_sensitive")
    if used:
        raise InvalidArgument(f"not supported before P2: {', '.join(used)}")


def _sample(spec: pb.UnitSpec):
    return sample_from_proto(spec.regression_sample) if spec.HasField("regression_sample") else None


def _draft(spec: pb.UnitSpec) -> UnitDraft:
    _reject_p2_fields(spec)
    return UnitDraft(token=spec.token, dimension=spec.dimension or None,
                     pint_definition=spec.pint_definition or None, aliases=tuple(spec.aliases),
                     depends_on=tuple(spec.depends_on), regression_sample=_sample(spec))


def _iso(value) -> str:
    return value.isoformat() if value else ""


def _type_response(unit_type: UnitType) -> pb.UnitTypeResponse:
    return pb.UnitTypeResponse(
        id=unit_type.id,
        spec=pb.UnitTypeSpec(code=unit_type.code, label=unit_type.label, description=unit_type.description or ""),
        is_active=unit_type.is_active,
        dimensions=list(unit_type.dimensions),
        created_by=unit_type.created_by,
        created_at=_iso(unit_type.created_at),
        updated_at=_iso(unit_type.updated_at),
    )


def _validation_response(outcome: ValidationOutcome) -> pb.ValidationResult:
    dry = outcome.dry_run
    dry_run = pb.DryRunResult(ok=dry.ok, canonical_value=dry.canonical_value or 0.0,
                              canonical_unit=dry.canonical_unit, bypassed=dry.bypassed, error=dry.error)
    if dry.canonical_max is not None:
        dry_run.canonical_max = dry.canonical_max
    return pb.ValidationResult(
        overall_ok=outcome.ok,
        guards=[pb.GuardResult(guard=g.guard, ok=g.ok, skipped=g.skipped, message=g.message) for g in outcome.guards],
        dry_run=dry_run,
    )


class UnitRegistryServicer(pb_grpc.UnitRegistryServiceServicer):
    def __init__(self, units: UnitService, types: TypeService):
        self._units = units
        self._types = types

    def _unit(self, unit: Unit, version: int = 0) -> pb.UnitResponse:
        return unit_to_proto(unit, registry_version=version, types=self._units.types_for([unit])[unit.id])

    # --- units -----------------------------------------------------------
    @_rpc
    def RegisterUnit(self, request, context):
        unit, version = self._units.register(_draft(request.spec), request.created_by or "unknown")
        return self._unit(unit, version)

    @_rpc
    def GetUnit(self, request, context):
        return self._unit(self._units.get(unit_id=request.id or None, token=request.token or None))

    @_rpc
    def ListUnits(self, request, context):
        try:
            status = UnitStatus(request.status) if request.status else None
        except ValueError:
            raise InvalidArgument(f"unknown status {request.status!r}")
        units, version = self._units.list(status=status, dimension=request.dimension or None,
                                          type_code=request.type or None)
        start = max(request.offset, 0)
        page = units[start:] if request.limit <= 0 else units[start:start + request.limit]
        types = self._units.types_for(page)
        return pb.ListUnitsResponse(units=[unit_to_proto(u, types=types[u.id]) for u in page],
                                    total=len(units), registry_version=version)

    @_rpc
    def UpdateUnit(self, request, context):
        if not request.id:
            raise InvalidArgument("'id' is required")
        paths = list(request.update_mask.paths)
        if not paths:
            raise InvalidArgument("update_mask must name at least one field")
        spec = request.spec
        values = {
            "dimension": lambda: spec.dimension or None,
            "pint_definition": lambda: spec.pint_definition or None,
            "aliases": lambda: tuple(spec.aliases),
            "depends_on": lambda: tuple(spec.depends_on),
            "regression_sample": lambda: _sample(spec),
        }
        changes = {}
        for path in paths:
            if path in _P2_ONLY or path in ("kind", "case_sensitive"):
                raise InvalidArgument(f"not supported before P2: {path}")
            if path not in values:
                raise InvalidArgument(f"field {path!r} cannot be updated; updatable: {', '.join(_UNIT_PATHS)}")
            changes[path] = values[path]()
        unit, version = self._units.update(request.id, changes, request.updated_by or "unknown")
        return self._unit(unit, version)

    @_rpc
    def DeleteUnit(self, request, context):
        if not request.id:
            raise InvalidArgument("'id' is required")
        self._units.disable(request.id, request.deleted_by or "unknown")
        return pb.DeleteUnitResponse(success=True)

    @_rpc
    def GetRegistryStatus(self, request, context):
        version, active = self._units.registry_status()
        return pb.RegistryStatus(loaded_version=version, active_unit_count=active)

    @_rpc
    def ValidateUnit(self, request, context):
        return _validation_response(self._units.validate(_draft(request.spec), unit_id=request.id or None))

    # --- unit types (C9) -------------------------------------------------
    @_rpc
    def CreateUnitType(self, request, context):
        spec = request.spec
        return _type_response(self._types.create(spec.code, spec.label, spec.description or None,
                                                 request.created_by or "unknown"))

    @_rpc
    def UpdateUnitType(self, request, context):
        paths = list(request.update_mask.paths)
        if "code" in paths:
            raise InvalidArgument("type code is immutable")
        if not paths:
            raise InvalidArgument("update_mask must name at least one field")
        unknown = [p for p in paths if p not in _TYPE_PATHS]
        if unknown:
            raise InvalidArgument(f"field {unknown[0]!r} cannot be updated; updatable: label, description")
        changes = {p: (getattr(request.spec, p) or None) for p in paths}
        return _type_response(self._types.update(request.id, changes, request.updated_by or "unknown"))

    @_rpc
    def DeactivateUnitType(self, request, context):
        return _type_response(self._types.deactivate(request.id, request.updated_by or "unknown"))

    @_rpc
    def GetUnitType(self, request, context):
        return _type_response(self._types.get(type_id=request.id or None, code=request.code or None))

    @_rpc
    def ListUnitTypes(self, request, context):
        return pb.ListUnitTypesResponse(
            types=[_type_response(t) for t in self._types.list(include_inactive=request.include_inactive)])

    @_rpc
    def SetDimensionTypes(self, request, context):
        codes = self._types.set_dimension_types(request.dimension, list(request.type_codes),
                                                request.updated_by or "unknown")
        return pb.DimensionTypesResponse(dimension=request.dimension, type_codes=codes)
```

- [ ] **Step 5: Write `server.py`**

`infrastructure/grpc/server.py`:

```python
from __future__ import annotations

from concurrent import futures

import grpc

from application.types_service import TypeService
from application.unit_service import UnitService
from grpc_stubs import unit_registry_pb2_grpc as pb_grpc

from .auth import AdminKeyInterceptor
from .servicer import UnitRegistryServicer


def build_server(units: UnitService, types: TypeService, *, admin_key: str, port: int,
                 max_workers: int = 10) -> tuple[grpc.Server, int]:
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=max_workers),
                         interceptors=[AdminKeyInterceptor(admin_key)])
    pb_grpc.add_UnitRegistryServiceServicer_to_server(UnitRegistryServicer(units, types), server)
    bound = server.add_insecure_port(f"[::]:{port}")
    return server, bound
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `scripts/unit-registry-test.sh apps-microservices/unit-registry-service -q`
Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add apps-microservices/unit-registry-service/infrastructure/grpc apps-microservices/unit-registry-service/tests/test_grpc.py
git commit -m "feat(unit-registry-service): gRPC servicer with admin-key interceptor" -m "EN: Serves the 13 UnitRegistryService RPCs; write RPCs require Bearer UNITS_ADMIN_KEY (constant-time compare), reads and ValidateUnit are open. Guard failures map to INVALID_ARGUMENT/ALREADY_EXISTS, dependents to FAILED_PRECONDITION, P2-only fields are refused." -m "FR : Sert les 13 RPC de UnitRegistryService ; les RPC d'ecriture exigent Bearer UNITS_ADMIN_KEY (comparaison a temps constant), lectures et ValidateUnit ouvertes. Echecs de garde-fous -> INVALID_ARGUMENT/ALREADY_EXISTS, dependances -> FAILED_PRECONDITION, champs P2 refuses."
```

---

### Task 10: Outbox relay + RabbitMQ publisher

**Files:**
- Create: `apps-microservices/unit-registry-service/infrastructure/messaging/__init__.py` (empty), `publisher.py`, `relay.py`
- Create: `apps-microservices/unit-registry-service/tests/test_relay.py`

**Interfaces:**
- Consumes: `UnitEventRow`, `application.clock.utcnow`.
- Produces:
  - the `infrastructure.messaging.publisher.Publisher` protocol (`publish(body: bytes)`, `heartbeat()`, `reset()`)
  - `PikaPublisher(url, exchange)`
  - `infrastructure.messaging.relay.OutboxRelay(session_factory, publisher, clock=utcnow, batch_size=100)`, with `run_once() -> int` and `run_forever(stop: threading.Event, poll_seconds: float)`

- [ ] **Step 1: Write the failing tests**

`apps-microservices/unit-registry-service/tests/test_relay.py`:

```python
import json
import threading

import pytest
from sqlalchemy import select

from application.unit_service import UnitDraft, UnitService
from infrastructure.db.models import UnitEventRow
from infrastructure.messaging.relay import OutboxRelay
from unit_registry.types import RegressionSample

from .conftest import NOW


class FakePublisher:
    def __init__(self, fail_on_call: int | None = None):
        self.bodies: list[dict] = []
        self.calls = 0
        self.fail_on_call = fail_on_call
        self.resets = 0

    def publish(self, body: bytes) -> None:
        self.calls += 1
        if self.calls == self.fail_on_call:
            raise ConnectionError("broker nack")
        self.bodies.append(json.loads(body))

    def heartbeat(self) -> None:
        pass

    def reset(self) -> None:
        self.resets += 1


@pytest.fixture
def three_events(seeded):
    service = UnitService(seeded, clock=lambda: NOW)
    for n, factor in enumerate((25, 30, 35)):
        service.register(UnitDraft(
            token=f"sac_{n}", dimension="mass", pint_definition=f"sac_{n} = {factor} * kilogram",
            regression_sample=RegressionSample(label="Poids", value="1", expected_canonical_value=float(factor),
                                               expected_canonical_unit="kilogram")), "tester")
    return seeded


def published_versions(factory):
    with factory() as s:
        return [r.registry_version for r in s.execute(select(UnitEventRow).order_by(UnitEventRow.id)).scalars()
                if r.published_at is not None]


def test_publishes_in_version_order_and_marks_rows(three_events):
    publisher = FakePublisher()
    assert OutboxRelay(three_events, publisher, clock=lambda: NOW).run_once() == 3
    assert [b["registry_version"] for b in publisher.bodies] == [2, 3, 4]
    assert published_versions(three_events) == [2, 3, 4]
    assert OutboxRelay(three_events, publisher, clock=lambda: NOW).run_once() == 0


def test_a_failed_publish_leaves_the_rest_for_the_next_run(three_events):
    with pytest.raises(ConnectionError):
        OutboxRelay(three_events, FakePublisher(fail_on_call=2), clock=lambda: NOW).run_once()
    assert published_versions(three_events) == [2]
    publisher = FakePublisher()
    assert OutboxRelay(three_events, publisher, clock=lambda: NOW).run_once() == 2
    assert [b["registry_version"] for b in publisher.bodies] == [3, 4]


def test_run_forever_resets_the_publisher_after_a_failure(three_events):
    stop = threading.Event()
    publisher = FakePublisher(fail_on_call=1)
    original_reset = publisher.reset

    def reset_then_stop():
        original_reset()
        stop.set()

    publisher.reset = reset_then_stop
    OutboxRelay(three_events, publisher, clock=lambda: NOW).run_forever(stop, poll_seconds=0.01)
    assert publisher.resets == 1
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `scripts/unit-registry-test.sh apps-microservices/unit-registry-service -q tests/test_relay.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'infrastructure.messaging'`.

- [ ] **Step 3: Write the publisher**

`infrastructure/messaging/publisher.py`:

```python
"""RabbitMQ publisher for the normalization.units fanout (publisher confirms on)."""
from __future__ import annotations

import logging
from typing import Protocol

import pika

logger = logging.getLogger(__name__)


class Publisher(Protocol):
    def publish(self, body: bytes) -> None: ...  # raises on nack or connection loss
    def heartbeat(self) -> None: ...
    def reset(self) -> None: ...


class PikaPublisher:
    def __init__(self, url: str, exchange: str):
        self._url = url
        self._exchange = exchange
        self._connection: pika.BlockingConnection | None = None
        self._channel = None

    def _ensure_channel(self):
        if self._channel is None or self._channel.is_closed:
            self._connection = pika.BlockingConnection(pika.URLParameters(self._url))
            self._channel = self._connection.channel()
            self._channel.exchange_declare(exchange=self._exchange, exchange_type="fanout", durable=True)
            self._channel.confirm_delivery()
        return self._channel

    def publish(self, body: bytes) -> None:
        self._ensure_channel().basic_publish(
            exchange=self._exchange,
            routing_key="",
            body=body,
            properties=pika.BasicProperties(content_type="application/json",
                                            delivery_mode=pika.DeliveryMode.Persistent),
        )

    def heartbeat(self) -> None:
        if self._connection is not None and self._connection.is_open:
            self._connection.process_data_events(time_limit=0)

    def reset(self) -> None:
        try:
            if self._connection is not None and self._connection.is_open:
                self._connection.close()
        except Exception:  # closing a broken connection may raise; nothing to recover
            logger.debug("ignoring error while closing RabbitMQ connection", exc_info=True)
        self._connection = None
        self._channel = None
```

- [ ] **Step 4: Write the relay**

`infrastructure/messaging/relay.py`:

```python
"""Outbox relay: publish unit_events rows in registry_version order, mark each after the broker acks.

A crash between publish and mark re-sends that event; replicas drop it as a duplicate
by registry_version, so delivery is at-least-once and never lossy (spec §5).
"""
from __future__ import annotations

import json
import logging
import threading
from datetime import datetime
from typing import Callable

from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from application.clock import utcnow
from infrastructure.db.models import UnitEventRow

from .publisher import Publisher

logger = logging.getLogger(__name__)


class OutboxRelay:
    def __init__(self, session_factory: sessionmaker[Session], publisher: Publisher,
                 clock: Callable[[], datetime] = utcnow, batch_size: int = 100):
        self._sf = session_factory
        self._publisher = publisher
        self._clock = clock
        self._batch_size = batch_size

    def run_once(self) -> int:
        with self._sf() as session:
            pending = session.execute(
                select(UnitEventRow.id, UnitEventRow.payload)
                .where(UnitEventRow.published_at.is_(None))
                .order_by(UnitEventRow.registry_version)
                .limit(self._batch_size)
            ).all()
        sent = 0
        for event_id, payload in pending:
            self._publisher.publish(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
            with self._sf.begin() as session:
                session.execute(update(UnitEventRow).where(UnitEventRow.id == event_id)
                                .values(published_at=self._clock()))
            sent += 1
        return sent

    def run_forever(self, stop: threading.Event, poll_seconds: float) -> None:
        while not stop.is_set():
            try:
                if self.run_once():
                    logger.info("published unit events")
                self._publisher.heartbeat()
                stop.wait(poll_seconds)
            except Exception:
                logger.exception("outbox relay failed; reconnecting")
                self._publisher.reset()
                stop.wait(min(poll_seconds * 5, 30.0))
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `scripts/unit-registry-test.sh apps-microservices/unit-registry-service -q`
Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add apps-microservices/unit-registry-service/infrastructure/messaging apps-microservices/unit-registry-service/tests/test_relay.py
git commit -m "feat(unit-registry-service): outbox relay publishing to the normalization.units fanout" -m "EN: Publishes pending unit_events in registry_version order with publisher confirms and marks each row only after the ack; a failed publish leaves the remainder for the next pass and resets the connection." -m "FR : Publie les unit_events en attente dans l'ordre de registry_version avec confirmations, et ne marque chaque ligne qu'apres l'accuse ; un echec laisse le reste pour le passage suivant et reinitialise la connexion."
```

---

### Task 11: Service entrypoint — config, HTTP health/metrics, main, Dockerfile, DB bootstrap script, docs

**Files:**
- Create: `apps-microservices/unit-registry-service/app/config.py`, `app/main.py`, `infrastructure/http_server.py`
- Create: `apps-microservices/unit-registry-service/Dockerfile`, `init-db/10_normalization_db.sh` (executable), `CLAUDE.md`
- Create: `apps-microservices/unit-registry-service/tests/test_http_and_config.py`

**Interfaces:**
- Produces:
  - `app.config.Settings`, with the properties `database_url: URL` and `UNITS_ADMIN_KEY` (min length 16)
  - `infrastructure.http_server.start_http_server(port, health_check, host="0.0.0.0") -> ThreadingHTTPServer`
  - `infrastructure.http_server.db_ping(engine) -> bool`
  - `app.main.main()`

- [ ] **Step 1: Write the failing tests**

`apps-microservices/unit-registry-service/tests/test_http_and_config.py`:

```python
import urllib.error
import urllib.request

import pytest
from pydantic import ValidationError

from app.config import Settings
from infrastructure.http_server import db_ping, start_http_server


def fetch(port, path):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=3) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


@pytest.mark.parametrize("healthy,code", [(True, 200), (False, 503)])
def test_health_reflects_the_check(healthy, code):
    server = start_http_server(0, lambda: healthy, host="127.0.0.1")
    try:
        assert fetch(server.server_address[1], "/health")[0] == code
    finally:
        server.shutdown()


def test_health_is_503_when_the_check_raises():
    def boom():
        raise RuntimeError("db down")

    server = start_http_server(0, boom, host="127.0.0.1")
    try:
        assert fetch(server.server_address[1], "/health")[0] == 503
    finally:
        server.shutdown()


def test_metrics_and_404():
    server = start_http_server(0, lambda: True, host="127.0.0.1")
    try:
        port = server.server_address[1]
        status, body = fetch(port, "/metrics")
        assert status == 200 and b"python_info" in body
        assert fetch(port, "/nope")[0] == 404
    finally:
        server.shutdown()


def test_db_ping(engine):
    assert db_ping(engine) is True


def settings(**overrides):
    values = dict(MYSQL_PASSWORD="p@ss", RABBITMQ_URL="amqp://guest:guest@rabbit:5672/",
                  UNITS_ADMIN_KEY="k" * 16)
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_database_url_is_built_from_parts():
    rendered = settings().database_url.render_as_string(hide_password=False)
    assert rendered == "mysql+pymysql://normalization_user:p%40ss@mysql:3306/normalization_db?charset=utf8mb4"


def test_admin_key_must_be_long_enough():
    with pytest.raises(ValidationError):
        settings(UNITS_ADMIN_KEY="short")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `scripts/unit-registry-test.sh apps-microservices/unit-registry-service -q tests/test_http_and_config.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.config'`.

- [ ] **Step 3: Write config and the HTTP server**

`app/config.py`:

```python
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True)

    GRPC_PORT: int = 50059
    GRPC_MAX_WORKERS: int = 10
    HTTP_PORT: int = 8571

    MYSQL_HOST: str = "mysql"
    MYSQL_PORT: int = 3306
    MYSQL_USER: str = "normalization_user"
    MYSQL_PASSWORD: str = Field(min_length=1)
    MYSQL_DB: str = "normalization_db"

    RABBITMQ_URL: str = Field(min_length=1)
    UNITS_EXCHANGE: str = "normalization.units"
    UNITS_ADMIN_KEY: str = Field(min_length=16)
    RELAY_POLL_SECONDS: float = 1.0

    @property
    def database_url(self) -> URL:
        return URL.create("mysql+pymysql", username=self.MYSQL_USER, password=self.MYSQL_PASSWORD,
                          host=self.MYSQL_HOST, port=self.MYSQL_PORT, database=self.MYSQL_DB,
                          query={"charset": "utf8mb4"})
```

`infrastructure/http_server.py`:

```python
"""Side HTTP server: /health (DB reachable) and /metrics (Prometheus)."""
from __future__ import annotations

import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable

from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)


def db_ping(engine: Engine) -> bool:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    return True


def _safe(check: Callable[[], bool]) -> bool:
    try:
        return bool(check())
    except Exception:
        logger.warning("health check failed", exc_info=True)
        return False


def start_http_server(port: int, health_check: Callable[[], bool], host: str = "0.0.0.0") -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 (http.server API)
            if self.path == "/health":
                healthy = _safe(health_check)
                body = b'{"status":"ok"}' if healthy else b'{"status":"unavailable"}'
                self._send(200 if healthy else 503, body, "application/json")
            elif self.path == "/metrics":
                self._send(200, generate_latest(), CONTENT_TYPE_LATEST)
            else:
                self._send(404, b"not found", "text/plain")

        def _send(self, code: int, body: bytes, content_type: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):  # noqa: A002 — silence per-request logs
            return

    server = ThreadingHTTPServer((host, port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True, name="http").start()
    return server
```

- [ ] **Step 4: Write `main.py`**

`app/main.py`:

```python
import logging
import threading

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import Settings
from application.clock import utcnow
from application.types_service import TypeService
from application.unit_service import UnitService
from infrastructure.db.bootstrap import bootstrap
from infrastructure.db.models import Base
from infrastructure.grpc.server import build_server
from infrastructure.http_server import db_ping, start_http_server
from infrastructure.messaging.publisher import PikaPublisher
from infrastructure.messaging.relay import OutboxRelay

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")


def main() -> None:
    settings = Settings()
    engine = create_engine(settings.database_url, pool_pre_ping=True, pool_recycle=3600)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(engine, expire_on_commit=False)
    with session_factory.begin() as session:
        bootstrap(session, utcnow())

    stop = threading.Event()
    relay = OutboxRelay(session_factory, PikaPublisher(settings.RABBITMQ_URL, settings.UNITS_EXCHANGE))
    threading.Thread(target=relay.run_forever, args=(stop, settings.RELAY_POLL_SECONDS),
                     daemon=True, name="outbox-relay").start()
    start_http_server(settings.HTTP_PORT, lambda: db_ping(engine))

    server, port = build_server(UnitService(session_factory), TypeService(session_factory),
                                admin_key=settings.UNITS_ADMIN_KEY, port=settings.GRPC_PORT,
                                max_workers=settings.GRPC_MAX_WORKERS)
    server.start()
    logging.info("unit-registry-service: gRPC on %d, HTTP on %d", port, settings.HTTP_PORT)
    try:
        server.wait_for_termination()
    finally:
        stop.set()


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Write the Dockerfile and the DB bootstrap script**

`apps-microservices/unit-registry-service/Dockerfile`:

```dockerfile
FROM python:3.10-slim

WORKDIR /app
ENV PYTHONPATH=/app PYTHONUNBUFFERED=1

COPY apps-microservices/unit-registry-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY libs /app/libs
COPY protos /app/protos
RUN python -m grpc_tools.protoc -I/app/protos --python_out=/app/libs/grpc-stubs/src \
      --grpc_python_out=/app/libs/grpc-stubs/src /app/protos/grpc_stubs/*.proto \
 && pip install --no-cache-dir -e /app/libs/grpc-stubs -e /app/libs/unit-registry

COPY apps-microservices/unit-registry-service/app ./app
COPY apps-microservices/unit-registry-service/application ./application
COPY apps-microservices/unit-registry-service/infrastructure ./infrastructure

RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin registry
USER registry

EXPOSE 50059 8571
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8571/health', timeout=3).status == 200 else 1)"
CMD ["python", "-m", "app.main"]
```

`apps-microservices/unit-registry-service/init-db/10_normalization_db.sh`:

```bash
#!/bin/bash
# Creates normalization_db and its user. Mounted into /docker-entrypoint-initdb.d of the
# `mysql` compose service, so it runs only on a FRESH volume. For an existing volume run it
# once by hand (see CLAUDE.md). Tables are created by the service itself (plan delta P7).
set -uo pipefail
if [ -z "${NORMALIZATION_MYSQL_PASS:-}" ]; then
  echo "[10_normalization_db] NORMALIZATION_MYSQL_PASS not set: skipping normalization_db" >&2
  exit 0
fi
user="${NORMALIZATION_MYSQL_USER:-normalization_user}"
mysql -uroot -p"${MYSQL_ROOT_PASSWORD}" <<SQL
CREATE DATABASE IF NOT EXISTS normalization_db CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
CREATE USER IF NOT EXISTS '${user}'@'%' IDENTIFIED BY '${NORMALIZATION_MYSQL_PASS}';
GRANT ALL PRIVILEGES ON normalization_db.* TO '${user}'@'%';
FLUSH PRIVILEGES;
SQL
```

Run: `chmod +x apps-microservices/unit-registry-service/init-db/10_normalization_db.sh`

- [ ] **Step 6: Write the service `CLAUDE.md`**

`apps-microservices/unit-registry-service/CLAUDE.md`:

````markdown
# unit-registry-service

Owns the normalization units (and unit types) in MySQL `normalization_db` and serves CRUD over gRPC
(`protos/grpc_stubs/unit_registry.proto`). Every unit write runs guards G1–G6 on the full registry, then
commits row + `registry_version` bump + outbox event in one transaction; a relay publishes the event to
the RabbitMQ fanout `normalization.units`, and every `graph-rag-normalize-unite-service` replica hot-reloads.
Spec: `docs/superpowers/specs/2026-10-06-unit-registry-combined-design.md`. Shared logic: `libs/unit-registry`.

## Tech Stack
Python 3.10, grpcio (sync server), SQLAlchemy 2 + PyMySQL, pika, prometheus-client, pydantic-settings, pint 0.24.4.

## Ports / Env
- gRPC **50059**, HTTP **8571** (`/health` = DB reachable, `/metrics`). Compose `expose` only.
- `MYSQL_HOST` / `MYSQL_PORT` / `MYSQL_USER` (`normalization_user`) / `MYSQL_PASSWORD` / `MYSQL_DB` (`normalization_db`)
- `RABBITMQ_URL`, `UNITS_EXCHANGE` (`normalization.units`), `UNITS_ADMIN_KEY` (≥ 16 chars; Bearer for write RPCs)

## Database bootstrap
`init-db/10_normalization_db.sh` creates the database and user, but only on a **fresh** `mysql` volume.
On the existing volume, run it once:
```bash
docker exec -i -e NORMALIZATION_MYSQL_PASS="$NORMALIZATION_MYSQL_PASS" mysql bash < apps-microservices/unit-registry-service/init-db/10_normalization_db.sh
```
Tables are created at startup (`create_all`); `bootstrap()` seeds the 36 dimensions, the 233 legacy units and the
`DIMENSION`/`CAPACITY` types when their tables are empty.

## Folder Structure
```
app/            config.py (Settings), main.py (wiring)
application/    unit_service.py, types_service.py, errors.py, models.py, clock.py
infrastructure/ db/ (models, repository, bootstrap), grpc/ (servicer, auth, server),
                messaging/ (publisher, relay), http_server.py
init-db/        10_normalization_db.sh
```

## Rules
- Write RPCs: RegisterUnit, UpdateUnit, DeleteUnit, CreateUnitType, UpdateUnitType, DeactivateUnitType, SetDimensionTypes.
- Unit types are metadata: they never bump `registry_version` and emit no event.
- P2-only fields (`kind`, `case_sensitive`, `rewrite_expression`, `label_condition`, `canonical_override`) are rejected.

## Tests
`scripts/unit-registry-test.sh apps-microservices/unit-registry-service -q` (SQLite). The real-MySQL collation test:
see `tests/test_mysql.py` (`MYSQL_TEST_URL`).

## Dependencies
- **Consumed by:** `mcp-normalize-unite-service` (gRPC), `graph-rag-normalize-unite-service` (`ListUnits` resync + events).
- **Depends on:** MySQL (`mysql` compose service), RabbitMQ.
````

- [ ] **Step 7: Run the tests and build the image**

Run: `scripts/unit-registry-test.sh apps-microservices/unit-registry-service -q`
Expected: all tests pass.
Run: `docker build -f apps-microservices/unit-registry-service/Dockerfile -t unit-registry-service:dev .`
Expected: the build succeeds.
Run: `docker run --rm=true unit-registry-service:dev python -c "import app.main, infrastructure.grpc.servicer; print('ok')"`
Expected: `ok`.

- [ ] **Step 8: Commit**

```bash
git add apps-microservices/unit-registry-service
git commit -m "feat(unit-registry-service): entrypoint, health/metrics, Dockerfile and DB bootstrap script" -m "EN: Wires DB bootstrap, the outbox relay thread, /health and /metrics on 8571 and the gRPC server on 50059. Non-root image; init-db script creates normalization_db and its user on fresh volumes and skips cleanly when unconfigured." -m "FR : Branche le bootstrap BDD, le thread du relais outbox, /health et /metrics sur 8571 et le serveur gRPC sur 50059. Image non-root ; le script init-db cree normalization_db et son utilisateur sur un volume neuf et s'ignore proprement s'il n'est pas configure."
```

---

### Task 12: Normalizer — state holder, registry client, event consumer, wiring

**Files:**
- Modify: `apps-microservices/graph-rag-normalize-unite-service/requirements.txt`, `Dockerfile`, `app/config.py`, `app/main.py`, `CLAUDE.md`
- Replace: `apps-microservices/graph-rag-normalize-unite-service/infrastructure/unit_normalization_service.py`
- Create: `infrastructure/unit_metrics.py`, `infrastructure/unit_state.py`, `infrastructure/registry_client.py`, `infrastructure/unit_events_consumer.py`
- Create: `tests/__init__.py` (empty), `tests/test_unit_state.py`, `tests/test_unit_events_consumer.py`, `tests/test_registry_client.py`, `tests/test_use_case_golden.py`

**Interfaces:**
- Consumes: `unit_registry.bundle.*`, `engine.Normalizer`, `events.make_event` / `parse_event`, `proto_codec.unit_from_proto` / `unit_to_proto`, `seed.build_seed_units`, and `ListUnits` from Task 9.
- Produces:
  - `infrastructure.unit_state.UnitStateHolder`, with `current()`, `load_full(units, version)`, `apply_event(event) -> "applied"|"duplicate"|"gap"` (raises `BundleBuildError`), `applied_version` and `source`
  - `RegistryClient(address, timeout=10.0)`, with `list_active() -> tuple[list[Unit], int]`
  - `UnitEventsConsumer(rabbitmq_url, exchange, holder, client, *, connect=None, max_backoff=60.0)`, with `resync()`, `handle_body(body) -> str` and `run_forever(stop)`
  - the module-level `unit_state` and `unit_normalizer` in `infrastructure.unit_normalization_service`

- [ ] **Step 1: Write the failing tests**

`tests/test_unit_state.py`:

```python
from dataclasses import replace
from datetime import datetime

import pytest

from infrastructure.unit_state import UnitStateHolder
from unit_registry.bundle import BundleBuildError
from unit_registry.engine import Normalizer
from unit_registry.events import EVENT_CREATED, EVENT_DISABLED, make_event
from unit_registry.seed import build_seed_units
from unit_registry.types import Unit, UnitStatus

NOW = datetime(2026, 10, 6, 12, 0, 0)
SAC = Unit(id="sac", token="sac_ciment", dimension="mass", pint_definition="sac_ciment = 25 * kilogram",
           sort_order=10_000)


@pytest.fixture(scope="module")
def seed():
    return build_seed_units()


def poids(holder, unit="sac_ciment"):
    return Normalizer(holder.current).normalize("Poids", unit, "2")


def test_starts_on_the_fallback_tables():
    holder = UnitStateHolder()
    assert holder.source == "fallback" and holder.applied_version == 0
    assert poids(holder, "kg") == {"valeur_canonique": 2.0, "unite_canonique": "kilogram"}


def test_event_on_fallback_requests_resync():
    holder = UnitStateHolder()
    assert holder.apply_event(make_event(EVENT_CREATED, 2, SAC, NOW)) == "gap"
    assert poids(holder) == {}


def test_load_then_apply_create_duplicate_gap_and_disable(seed):
    holder = UnitStateHolder()
    holder.load_full(seed, 1)
    assert holder.source == "db" and holder.applied_version == 1
    assert holder.apply_event(make_event(EVENT_CREATED, 2, SAC, NOW)) == "applied"
    assert poids(holder) == {"valeur_canonique": 50.0, "unite_canonique": "kilogram"}
    assert holder.apply_event(make_event(EVENT_CREATED, 2, SAC, NOW)) == "duplicate"
    assert holder.apply_event(make_event(EVENT_CREATED, 4, SAC, NOW)) == "gap"
    disabled = replace(SAC, status=UnitStatus.DISABLED)
    assert holder.apply_event(make_event(EVENT_DISABLED, 3, disabled, NOW)) == "applied"
    assert poids(holder) == {}


def test_a_build_failure_keeps_the_last_good_bundle(seed):
    holder = UnitStateHolder()
    holder.load_full(seed, 1)
    before = holder.current()
    clash = Unit(id="x", token="clash", dimension="volume", aliases=("kg",))
    with pytest.raises(BundleBuildError):
        holder.apply_event(make_event(EVENT_CREATED, 2, clash, NOW))
    assert holder.current() is before and holder.applied_version == 1


def test_a_request_keeps_the_bundle_it_started_with(seed):
    holder = UnitStateHolder()
    holder.load_full(seed, 1)
    old = holder.current()
    holder.apply_event(make_event(EVENT_CREATED, 2, SAC, NOW))
    assert Normalizer(lambda: old).normalize("Poids", "sac_ciment", "2") == {}
    assert poids(holder)["valeur_canonique"] == 50.0
```

`tests/test_unit_events_consumer.py`:

```python
import json
import threading
from datetime import datetime

from infrastructure.unit_events_consumer import UnitEventsConsumer
from infrastructure.unit_state import UnitStateHolder
from unit_registry.events import EVENT_CREATED, make_event
from unit_registry.seed import build_seed_units
from unit_registry.types import Unit

NOW = datetime(2026, 10, 6, 12, 0, 0)
SAC = Unit(id="sac", token="sac_ciment", dimension="mass", pint_definition="sac_ciment = 25 * kilogram",
           sort_order=10_000)


class FakeClient:
    def __init__(self, units, version):
        self.units, self.version, self.calls = units, version, 0

    def list_active(self):
        self.calls += 1
        return list(self.units), self.version


def consumer(holder, client, connect=None):
    return UnitEventsConsumer("amqp://unused", "normalization.units", holder, client, connect=connect)


def test_gap_triggers_a_full_resync():
    holder = UnitStateHolder()
    client = FakeClient([*build_seed_units(), SAC], 5)
    result = consumer(holder, client).handle_body(json.dumps(make_event(EVENT_CREATED, 5, SAC, NOW)).encode())
    assert result == "gap" and client.calls == 1
    assert holder.applied_version == 5 and holder.source == "db"


def test_invalid_payloads_are_dropped():
    holder = UnitStateHolder()
    c = consumer(holder, FakeClient([], 1))
    assert c.handle_body(b"not json") == "invalid"
    assert c.handle_body(b'{"event": "unit.created"}') == "invalid"


def test_initial_resync_happens_even_when_rabbitmq_is_down():
    holder = UnitStateHolder()
    client = FakeClient(build_seed_units(), 3)
    stop = threading.Event()

    def connect():
        stop.set()
        raise ConnectionError("rabbitmq down")

    consumer(holder, client, connect=connect).run_forever(stop)
    assert holder.source == "db" and holder.applied_version == 3
```

`tests/test_registry_client.py`:

```python
from concurrent import futures

import grpc

from grpc_stubs import unit_registry_pb2 as pb
from grpc_stubs import unit_registry_pb2_grpc as pb_grpc
from infrastructure.registry_client import RegistryClient
from unit_registry.proto_codec import unit_to_proto
from unit_registry.types import Unit

SAC = Unit(id="sac", token="sac_ciment", dimension="mass", pint_definition="sac_ciment = 25 * kilogram",
           sort_order=10_000)


class Servicer(pb_grpc.UnitRegistryServiceServicer):
    def __init__(self):
        self.requests = []

    def ListUnits(self, request, context):
        self.requests.append(request)
        return pb.ListUnitsResponse(units=[unit_to_proto(SAC)], total=1, registry_version=7)


def test_list_active_asks_for_every_active_unit():
    servicer = Servicer()
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=2))
    pb_grpc.add_UnitRegistryServiceServicer_to_server(servicer, server)
    port = server.add_insecure_port("localhost:0")
    server.start()
    try:
        units, version = RegistryClient(f"localhost:{port}").list_active()
    finally:
        server.stop(None)
    assert units == [SAC] and version == 7
    assert servicer.requests[0].status == "ACTIVE" and servicer.requests[0].limit == 0
```

`tests/test_use_case_golden.py`:

```python
"""The service (use case + wired engine on fallback tables) still matches the pre-move golden output."""
import json
from pathlib import Path

from application.normalization_use_case import NormalizationUseCase

GOLDEN = Path(__file__).resolve().parents[3] / "libs" / "unit-registry" / "tests" / "golden" / "golden.json"


def test_use_case_reproduces_golden_cases():
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    use_case = NormalizationUseCase()
    mismatches = []
    for case in golden["cases"]:
        if case["kind"] == "q":
            got = use_case.normalize_quantity(case["label"], case["unit"], case["value"], case["data_type"])
        else:
            got = use_case.normalize_range(case["label"], case["unit"], case["min"], case["max"])
        if got != case["out"]:
            mismatches.append({"case": case, "got": got})
    assert not mismatches, mismatches[:5]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `scripts/unit-registry-test.sh apps-microservices/graph-rag-normalize-unite-service -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'infrastructure.unit_state'` (and others). `test_use_case_golden.py` may already pass against the old engine; that's expected.

- [ ] **Step 3: Write metrics and the state holder**

`infrastructure/unit_metrics.py`:

```python
from prometheus_client import Counter, Gauge, Histogram

APPLIED_VERSION = Gauge("unit_registry_applied_version", "registry_version applied by this replica")
EVENTS = Counter("unit_registry_events_total", "Unit events received", ["result"])
SOURCE = Gauge("unit_registry_source", "1 for the unit-table source in use", ["source"])
BUILD_SECONDS = Histogram("unit_registry_build_seconds", "Time to build a RegistryBundle")
BUILD_FAILURES = Counter("unit_registry_build_failures_total", "RegistryBundle builds that failed")
RESYNCS = Counter("unit_registry_resync_total", "Full unit reloads from unit-registry-service")


def set_source(source: str) -> None:
    for name in ("db", "fallback"):
        SOURCE.labels(name).set(1 if name == source else 0)
```

`infrastructure/unit_state.py`:

```python
"""Process-wide unit tables with build-new-then-swap updates (spec §3.2, §5).

Readers call current() once per request and keep that bundle; writers (the event
consumer thread) build a new bundle off to the side and reassign one attribute.
"""
from __future__ import annotations

import threading
import time
from typing import Callable, Iterable, Mapping

from unit_registry.bundle import BundleBuildError, RegistryBundle, bundle_from_units, legacy_bundle
from unit_registry.events import parse_event
from unit_registry.types import Unit, UnitStatus

from .unit_metrics import APPLIED_VERSION, BUILD_FAILURES, BUILD_SECONDS, set_source


class UnitStateHolder:
    def __init__(self, build: Callable[[Iterable[Unit]], RegistryBundle] = bundle_from_units,
                 fallback: Callable[[], RegistryBundle] = legacy_bundle):
        self._build = build
        self._write_lock = threading.Lock()
        self._bundle = fallback()
        self._units: dict[str, Unit] = {}
        self.applied_version = 0
        self.source = "fallback"
        set_source("fallback")

    def current(self) -> RegistryBundle:
        return self._bundle

    def _timed_build(self, units: Iterable[Unit]) -> RegistryBundle:
        started = time.perf_counter()
        try:
            bundle = self._build(list(units))
        except BundleBuildError:
            BUILD_FAILURES.inc()
            raise
        BUILD_SECONDS.observe(time.perf_counter() - started)
        return bundle

    def load_full(self, units: Iterable[Unit], version: int) -> None:
        active = {u.id: u for u in units if u.status is UnitStatus.ACTIVE}
        with self._write_lock:
            bundle = self._timed_build(active.values())
            self._units = active
            self.applied_version = version
            self.source = "db"
            self._bundle = bundle
        APPLIED_VERSION.set(version)
        set_source("db")

    def apply_event(self, event: Mapping) -> str:
        _kind, version, unit = parse_event(event)
        with self._write_lock:
            if self.source != "db":
                return "gap"  # never patch the fallback tables: load from the registry first
            if version <= self.applied_version:
                return "duplicate"
            if version > self.applied_version + 1:
                return "gap"
            units = dict(self._units)
            if unit.status is UnitStatus.ACTIVE:
                units[unit.id] = unit
            else:
                units.pop(unit.id, None)
            bundle = self._timed_build(units.values())  # raises -> state untouched
            self._units = units
            self.applied_version = version
            self._bundle = bundle
        APPLIED_VERSION.set(version)
        return "applied"
```

- [ ] **Step 4: Write the registry client and the consumer**

`infrastructure/registry_client.py`:

```python
from __future__ import annotations

import grpc

from grpc_stubs import unit_registry_pb2 as pb
from grpc_stubs import unit_registry_pb2_grpc as pb_grpc
from unit_registry.proto_codec import unit_from_proto
from unit_registry.types import Unit


class RegistryClient:
    def __init__(self, address: str, timeout: float = 10.0):
        self._stub = pb_grpc.UnitRegistryServiceStub(grpc.insecure_channel(address))
        self._timeout = timeout

    def list_active(self) -> tuple[list[Unit], int]:
        response = self._stub.ListUnits(pb.ListUnitsRequest(status="ACTIVE", limit=0), timeout=self._timeout)
        return [unit_from_proto(u) for u in response.units], response.registry_version
```

`infrastructure/unit_events_consumer.py`:

```python
"""Consumes the normalization.units fanout and keeps UnitStateHolder in sync (spec §5)."""
from __future__ import annotations

import json
import logging
import threading
from typing import Callable

import pika

from unit_registry.bundle import BundleBuildError

from .unit_metrics import EVENTS, RESYNCS
from .unit_state import UnitStateHolder

logger = logging.getLogger(__name__)


class UnitEventsConsumer:
    def __init__(self, rabbitmq_url: str, exchange: str, holder: UnitStateHolder, client, *,
                 connect: Callable[[], object] | None = None, max_backoff: float = 60.0):
        self._exchange = exchange
        self._holder = holder
        self._client = client
        self._connect = connect or (lambda: pika.BlockingConnection(pika.URLParameters(rabbitmq_url)))
        self._max_backoff = max_backoff

    def resync(self) -> None:
        units, version = self._client.list_active()
        self._holder.load_full(units, version)
        RESYNCS.inc()
        logger.info("loaded %d active units at registry_version %d", len(units), version)

    def handle_body(self, body: bytes) -> str:
        try:
            event = json.loads(body)
        except ValueError:
            logger.error("dropping a non-JSON unit event")
            EVENTS.labels("invalid").inc()
            return "invalid"
        try:
            result = self._holder.apply_event(event)
        except BundleBuildError:
            logger.exception("unit event breaks the registry; keeping the last good tables")
            EVENTS.labels("failed").inc()
            return "failed"
        except (KeyError, TypeError, ValueError):
            logger.exception("dropping a malformed unit event")
            EVENTS.labels("invalid").inc()
            return "invalid"
        EVENTS.labels(result).inc()
        if result == "gap":
            self.resync()
        return result

    def _try_resync(self) -> None:
        try:
            self.resync()
        except Exception:
            logger.warning("initial unit load failed; serving %s tables", self._holder.source, exc_info=True)

    def run_forever(self, stop: threading.Event) -> None:
        self._try_resync()  # best effort even if RabbitMQ is down (Review Focus 3)
        backoff = 1.0
        while not stop.is_set():
            connection = None
            try:
                connection = self._connect()
                channel = connection.channel()
                channel.exchange_declare(exchange=self._exchange, exchange_type="fanout", durable=True)
                queue = channel.queue_declare(queue="", exclusive=True, auto_delete=True).method.queue
                channel.queue_bind(queue=queue, exchange=self._exchange)
                self.resync()  # after binding: nothing published from now on can be missed
                backoff = 1.0
                for _method, _properties, body in channel.consume(queue, auto_ack=True, inactivity_timeout=1.0):
                    if stop.is_set():
                        break
                    if body is not None:
                        self.handle_body(body)
            except Exception:
                logger.exception("unit events consumer failed; reconnecting in %.0fs", backoff)
                stop.wait(backoff)
                backoff = min(backoff * 2, self._max_backoff)
            finally:
                if connection is not None and getattr(connection, "is_open", False):
                    try:
                        connection.close()
                    except Exception:
                        logger.debug("ignoring error while closing RabbitMQ connection", exc_info=True)
```

- [ ] **Step 5: Shrink the engine module and wire it up**

Replace the **entire** content of `infrastructure/unit_normalization_service.py` with:

```python
"""Unit normalization wiring. The engine and the frozen tables now live in libs/unit-registry;
this module owns the process-wide state that the event consumer keeps in sync."""
from unit_registry.engine import Normalizer

from infrastructure.unit_state import UnitStateHolder

unit_state = UnitStateHolder()
unit_normalizer = Normalizer(unit_state.current)
```

In `app/config.py`, add these fields to `Settings` after `PROMETHEUS_PORT`:

```python
    # Live unit updates (empty RABBITMQ_URL = serve the frozen fallback tables only)
    RABBITMQ_URL: str = ""
    UNITS_EXCHANGE: str = "normalization.units"
    UNIT_REGISTRY_GRPC_ADDR: str = "unit-registry-service:50059"
```

Replace `app/main.py` with:

```python
import logging
import threading

from app.config import settings
from application.normalization_use_case import NormalizationUseCase
from common_utils.metrics.prometheus import start_metrics_server_in_thread
from infrastructure.grpc_server import serve
from infrastructure.registry_client import RegistryClient
from infrastructure.unit_events_consumer import UnitEventsConsumer
from infrastructure.unit_normalization_service import unit_state

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


def main():
    start_metrics_server_in_thread(port=settings.PROMETHEUS_PORT)

    if settings.RABBITMQ_URL:
        consumer = UnitEventsConsumer(
            settings.RABBITMQ_URL,
            settings.UNITS_EXCHANGE,
            unit_state,
            RegistryClient(settings.UNIT_REGISTRY_GRPC_ADDR),
        )
        threading.Thread(target=consumer.run_forever, args=(threading.Event(),),
                         daemon=True, name="unit-events").start()
    else:
        logging.warning("RABBITMQ_URL is not set: serving the frozen fallback unit tables, live updates disabled")

    use_case = NormalizationUseCase()

    logging.info("Starting Graph RAG Normalize Unite Service...")
    serve(use_case)


if __name__ == "__main__":
    main()
```

In `requirements.txt`, replace the line `pint` with `pint==0.24.4`, add a line `pika==1.3.2`, and remove the duplicated `waitress` line (keep one).

In `Dockerfile`, after `RUN pip install -e /app/libs/common-utils` add:

```dockerfile
RUN pip install -e /app/libs/unit-registry
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `scripts/unit-registry-test.sh apps-microservices/graph-rag-normalize-unite-service -q`
Expected: all tests pass (≈ 10 tests, including the golden replay through the use case).
Run: `scripts/unit-registry-test.sh libs/unit-registry -q`
Expected: still all green.
Run: `docker build -f apps-microservices/graph-rag-normalize-unite-service/Dockerfile -t normalize-unite:dev .`
Expected: the build succeeds.

- [ ] **Step 7: Update the normalizer's `CLAUDE.md`**

In `apps-microservices/graph-rag-normalize-unite-service/CLAUDE.md`:
- Under **Tech Stack**, add: ``- **Unit tables:** `libs/unit-registry` (engine + frozen fallback); live units from unit-registry-service``.
- Replace the `infrastructure/` lines of the **Folder Structure** block with:

```
infrastructure/
  grpc_server.py                   # gRPC server definition
  unit_normalization_service.py    # wiring: unit_state + Normalizer (engine lives in libs/unit-registry)
  unit_state.py                    # UnitStateHolder: build-new-then-swap bundle, version/gap logic
  unit_events_consumer.py          # RabbitMQ fanout `normalization.units` consumer + resync
  registry_client.py               # ListUnits(status=ACTIVE) on unit-registry-service
  unit_metrics.py                  # unit_registry_* Prometheus metrics
```

- Add a section:

```markdown
## Live units
- Boots on the frozen fallback tables, then loads every ACTIVE unit from `unit-registry-service`
  (`UNIT_REGISTRY_GRPC_ADDR`) and follows the `normalization.units` fanout (`RABBITMQ_URL`, `UNITS_EXCHANGE`).
- Each event patches one unit, rebuilds the pint registry off to the side (~0.3 s) and swaps it; a version gap
  or a reconnect triggers a full reload. Empty `RABBITMQ_URL` = fallback tables only.
- Never add a unit in code: use the `create_unit` MCP tool / `RegisterUnit` RPC.
- Tests: `scripts/unit-registry-test.sh apps-microservices/graph-rag-normalize-unite-service -q`.
```

- [ ] **Step 8: Commit**

```bash
git add apps-microservices/graph-rag-normalize-unite-service
git commit -m "feat(graph-rag-normalize-unite-service): hot-reload units from unit-registry-service events" -m "EN: The engine now comes from libs/unit-registry and reads a swappable RegistryBundle. A consumer follows the normalization.units fanout: one unit patched per event, gap or reconnect -> full ListUnits resync, build failure keeps the last good tables, fallback tables until the first load." -m "FR : Le moteur vient de libs/unit-registry et lit un RegistryBundle permutable. Un consommateur suit le fanout normalization.units : une unite corrigee par evenement, trou ou reconnexion -> resynchronisation ListUnits complete, un echec de construction garde les dernieres tables valides, tables de secours jusqu'au premier chargement."
```

---

### Task 13: docker-compose wiring

**Files:**
- Modify: `docker-compose.yml` (the `mysql`, `graph-rag-normalize-unite-service` and `mcp-normalize-unite-service` blocks, plus a new `unit-registry-service` block)

**Interfaces:**
- Consumes: ports, env names and the init script from Tasks 11–12, plus the MCP env used in Task 14.

- [ ] **Step 1: Add the `mysql` env and the init-script mount**

In the `mysql:` service, append to `environment:`:

```yaml
      - NORMALIZATION_MYSQL_USER=${NORMALIZATION_MYSQL_USER:-normalization_user}
      - NORMALIZATION_MYSQL_PASS=${NORMALIZATION_MYSQL_PASS:-}
```

and append to `volumes:`:

```yaml
      - ./apps-microservices/unit-registry-service/init-db/10_normalization_db.sh:/docker-entrypoint-initdb.d/10_normalization_db.sh:ro
```

- [ ] **Step 2: Add the `unit-registry-service` block right after `graph-rag-normalize-unite-service`**

```yaml
  unit-registry-service:
    build:
      context: .
      dockerfile: apps-microservices/unit-registry-service/Dockerfile
    profiles: [ "graph-rag", "mcp" ]
    restart: unless-stopped
    expose:
      - "50059"
      - "8571"
    environment:
      MYSQL_HOST: mysql
      MYSQL_PORT: ${GATEWAY_MYSQL_PORT:-3306}
      MYSQL_USER: ${NORMALIZATION_MYSQL_USER:-normalization_user}
      MYSQL_PASSWORD: ${NORMALIZATION_MYSQL_PASS:-}
      MYSQL_DB: normalization_db
      RABBITMQ_URL: ${RABBITMQ_URL}
      UNITS_EXCHANGE: normalization.units
      UNITS_ADMIN_KEY: ${UNITS_ADMIN_KEY:-}
    healthcheck:
      test: [ "CMD", "python", "-c", "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8571/health', timeout=3).status == 200 else 1)" ]
      interval: 30s
      timeout: 5s
      retries: 3
    networks:
      - services-net
    logging: *logging_defaults
```

- [ ] **Step 3: Add the env to the normalizer**

In `graph-rag-normalize-unite-service:` → `environment:` (after `PROMETHEUS_PORT: 8567`):

```yaml
      RABBITMQ_URL: ${RABBITMQ_URL}
      UNITS_EXCHANGE: normalization.units
      UNIT_REGISTRY_GRPC_ADDR: unit-registry-service:50059
```

- [ ] **Step 4: Add the env to the MCP server**

In `mcp-normalize-unite-service:` → `environment:`:

```yaml
      - UNIT_REGISTRY_GRPC_ADDR=unit-registry-service:50059
      - UNITS_ADMIN_KEY=${UNITS_ADMIN_KEY:-}
```

- [ ] **Step 5: Validate the compose file**

Run: `RABBITMQ_URL=amqp://x docker compose --profile graph-rag --profile mcp config --quiet && echo compose-ok`
Expected: `compose-ok`.
Run: `RABBITMQ_URL=amqp://x docker compose --profile graph-rag config --services | grep -x unit-registry-service`
Expected: `unit-registry-service`.

- [ ] **Step 6: Commit**

```bash
git add docker-compose.yml
git commit -m "chore(compose): wire unit-registry-service, normalizer events and MCP registry access" -m "EN: Adds unit-registry-service (gRPC 50059, HTTP 8571, expose only, healthcheck), mounts its normalization_db init script into mysql, and passes RABBITMQ_URL/UNIT_REGISTRY_GRPC_ADDR to the normalizer and UNITS_ADMIN_KEY to the MCP server." -m "FR : Ajoute unit-registry-service (gRPC 50059, HTTP 8571, expose seulement, healthcheck), monte son script d'init normalization_db dans mysql, et passe RABBITMQ_URL/UNIT_REGISTRY_GRPC_ADDR au normaliseur et UNITS_ADMIN_KEY au serveur MCP."
```

---

### Task 14: MCP — stubs, config, clients, and the 4 unit tools

**Files:**
- Create: `scripts/mcp-normalize-test.sh`
- Modify: `apps-microservices/mcp-normalize-unite-service/proto/generate.sh`, `Dockerfile`, `internal/config/config.go`, `cmd/server/main.go`, `internal/tools/registry.go`, `internal/tools/normalize_test.go` (`TestToolsList` only)
- Create: `apps-microservices/mcp-normalize-unite-service/internal/tools/units.go`, `internal/tools/units_test.go`

**Interfaces:**
- Consumes: the Go package `unit_registry` generated from Task 5's proto, and the existing helpers `requiredString`, `optionalString`, `quantityValue`, `optionalNumber`, `formatNumber`, `contains`, `allowedDataTypes`, `errorResult`, `jsonResult`, plus the test helpers `decode`, `wantError`, `fakeNormalization`.
- Produces:
  - `Clients.Units unitregistrypb.UnitRegistryServiceClient`, `Clients.UnitsAdminKey string`, `Clients.Actor string`
  - helpers `registryCtx`, `registryError`, `stringList`, `orEmpty`
  - tools `create_unit`, `update_unit`, `deactivate_unit`, `get_unit`
  - the test helpers `fakeRegistry`, `newFakeRegistry()`, `callRegistry` and `testAdminKey` (reused by Task 15)

- [ ] **Step 1: Create the Go test runner**

`scripts/mcp-normalize-test.sh`:

```bash
#!/usr/bin/env bash
# Generate Go stubs and run vet + tests for mcp-normalize-unite-service in a persistent container.
# The service is copied to /work inside the container, so go.sum and proto/gen never land in the repo.
# Usage: scripts/mcp-normalize-test.sh [go test args, default ./...]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
NAME=mcp-normalize-go-test

mounted="$(docker inspect -f '{{range .Mounts}}{{if eq .Destination "/repo"}}{{.Source}}{{end}}{{end}}' "$NAME" 2>/dev/null || true)"
running="$(docker inspect -f '{{.State.Running}}' "$NAME" 2>/dev/null || true)"
if [ "$mounted" != "$ROOT" ] || [ "$running" != "true" ]; then
  docker rm -f "$NAME" >/dev/null 2>&1 || true
  docker run -d --name "$NAME" -v "$ROOT:/repo:ro" \
    -v mcp-normalize-gomod:/go/pkg/mod -v mcp-normalize-gocache:/root/.cache/go-build \
    golang:1.24-alpine sleep infinity >/dev/null
  docker exec "$NAME" sh -c 'apk add --no-cache bash protobuf protobuf-dev >/dev/null \
    && go install google.golang.org/protobuf/cmd/protoc-gen-go@v1.36.6 \
    && go install google.golang.org/grpc/cmd/protoc-gen-go-grpc@v1.5.1'
fi

docker exec "$NAME" sh -c "rm -rf /work && cp -r /repo/apps-microservices/mcp-normalize-unite-service /work \
  && cd /work && PROTO_DIR=/repo/protos/grpc_stubs bash proto/generate.sh >/dev/null \
  && go mod tidy && go vet ./... && go test ${*:-./...}"
```

Run: `chmod +x scripts/mcp-normalize-test.sh`

- [ ] **Step 2: Generate `unit_registry` stubs in the script and the Dockerfile**

In `proto/generate.sh`, change the `PROTOS` map to:

```bash
declare -A PROTOS=(
  [graph_normalization]="graph_normalization.proto"
  [unit_registry]="unit_registry.proto"
)
```

In `Dockerfile` (protogen stage), replace the line `COPY protos/grpc_stubs/graph_normalization.proto /protos/grpc_stubs/` with:

```dockerfile
COPY protos/grpc_stubs/graph_normalization.proto protos/grpc_stubs/unit_registry.proto /protos/grpc_stubs/
```

and add this right after the existing `RUN mkdir -p /build/proto/gen/graph_normalization && \ ...` block:

```dockerfile
RUN mkdir -p /build/proto/gen/unit_registry && \
    protoc --proto_path=/protos/grpc_stubs \
        --go_out=/build/proto/gen/unit_registry --go_opt=paths=source_relative \
        --go_opt=Munit_registry.proto=${MOD}/unit_registry \
        --go-grpc_out=/build/proto/gen/unit_registry --go-grpc_opt=paths=source_relative \
        --go-grpc_opt=Munit_registry.proto=${MOD}/unit_registry \
        /protos/grpc_stubs/unit_registry.proto
```

- [ ] **Step 3: Extend config, clients and main**

In `internal/config/config.go`, add to `Config`:

```go
	// unit-registry-service (unit CRUD); UnitsAdminKey is the Bearer for its write RPCs.
	UnitRegistryAddr string
	UnitsAdminKey    string
```

and in `Load()`:

```go
		UnitRegistryAddr: getEnv("UNIT_REGISTRY_GRPC_ADDR", "unit-registry-service:50059"),
		UnitsAdminKey:    os.Getenv("UNITS_ADMIN_KEY"),
```

In `internal/tools/registry.go`, replace the import block and the `Clients` struct with:

```go
import (
	"context"
	"encoding/json"
	"fmt"
	"log"

	"github.com/hellopro/mcp-normalize-unite/internal/mcp"
	normalizationpb "github.com/hellopro/mcp-normalize-unite/proto/gen/graph_normalization"
	unitregistrypb "github.com/hellopro/mcp-normalize-unite/proto/gen/unit_registry"
)

// Clients holds persistent gRPC connections to backend services.
type Clients struct {
	Normalization normalizationpb.GraphNormalizationServiceClient
	Units         unitregistrypb.UnitRegistryServiceClient
	// UnitsAdminKey is sent as "authorization: Bearer <key>" on unit-registry writes only.
	UnitsAdminKey string
	// Actor is recorded as created_by / updated_by on unit-registry writes.
	Actor string
}
```

and in `NewRegistry`, after the two `normalize_*` registrations:

```go
	r.register("create_unit", createUnitDescription, createUnitInputSchema, handleCreateUnit)
	r.register("update_unit", updateUnitDescription, updateUnitInputSchema, handleUpdateUnit)
	r.register("deactivate_unit", deactivateUnitDescription, unitRefInputSchema, handleDeactivateUnit)
	r.register("get_unit", getUnitDescription, unitRefInputSchema, handleGetUnit)
```

In `cmd/server/main.go`, add the import `unitregistrypb "github.com/hellopro/mcp-normalize-unite/proto/gen/unit_registry"`, then right after `defer normalizationConn.Close()` add:

```go
	unitRegistryConn := mustDial(cfg.UnitRegistryAddr, "unit-registry")
	defer unitRegistryConn.Close()
	if cfg.UnitsAdminKey == "" {
		log.Printf("[main] UNITS_ADMIN_KEY is empty: unit write tools will be rejected by unit-registry-service")
	}
```

and replace the `clients := &tools.Clients{...}` literal with:

```go
	clients := &tools.Clients{
		Normalization: normalizationpb.NewGraphNormalizationServiceClient(normalizationConn),
		Units:         unitregistrypb.NewUnitRegistryServiceClient(unitRegistryConn),
		UnitsAdminKey: cfg.UnitsAdminKey,
		Actor:         "mcp:" + cfg.Name,
	}
```

- [ ] **Step 4: Write the failing tests**

In `internal/tools/normalize_test.go`, change the expected names in `TestToolsList` to:

```go
	if strings.Join(names, ",") != "normalize_quantity,normalize_range,create_unit,update_unit,deactivate_unit,get_unit" {
```

`internal/tools/units_test.go`:

```go
package tools

import (
	"context"
	"encoding/json"
	"errors"
	"sync"
	"testing"

	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/metadata"
	"google.golang.org/grpc/status"

	"github.com/hellopro/mcp-normalize-unite/internal/mcp"
	unitregistrypb "github.com/hellopro/mcp-normalize-unite/proto/gen/unit_registry"
)

const testAdminKey = "test-admin-key-0123456789"

// fakeRegistry records every call, the authorization metadata it carried, and the last request per RPC.
type fakeRegistry struct {
	mu          sync.Mutex
	calls       []string
	auth        map[string]string
	units       map[string]*unitregistrypb.UnitResponse     // by token
	types       map[string]*unitregistrypb.UnitTypeResponse // by code
	err         error
	lastReg     *unitregistrypb.RegisterUnitRequest
	lastUpdate  *unitregistrypb.UpdateUnitRequest
	lastDelete  *unitregistrypb.DeleteUnitRequest
	lastGet     *unitregistrypb.GetUnitRequest
	lastCreateT *unitregistrypb.CreateUnitTypeRequest
	lastUpdateT *unitregistrypb.UpdateUnitTypeRequest
	lastDeactT  *unitregistrypb.DeactivateUnitTypeRequest
	lastGetT    *unitregistrypb.GetUnitTypeRequest
	lastSetDims *unitregistrypb.SetDimensionTypesRequest
}

func newFakeRegistry() *fakeRegistry {
	return &fakeRegistry{
		auth: map[string]string{},
		units: map[string]*unitregistrypb.UnitResponse{
			"kg": {Id: "u-kg", Spec: &unitregistrypb.UnitSpec{Token: "kg", Dimension: "mass"}, Status: "ACTIVE", Source: "seed", Types: []string{"CAPACITY"}},
		},
		types: map[string]*unitregistrypb.UnitTypeResponse{
			"CAPACITY": {Id: "t-cap", Spec: &unitregistrypb.UnitTypeSpec{Code: "CAPACITY", Label: "Capacité"}, IsActive: true},
		},
	}
}

func (f *fakeRegistry) record(ctx context.Context, method string) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.calls = append(f.calls, method)
	if md, ok := metadata.FromOutgoingContext(ctx); ok {
		if v := md.Get("authorization"); len(v) > 0 {
			f.auth[method] = v[0]
		}
	}
	if _, ok := ctx.Deadline(); !ok {
		return errors.New("call has no deadline")
	}
	return f.err
}

func (f *fakeRegistry) RegisterUnit(ctx context.Context, in *unitregistrypb.RegisterUnitRequest, _ ...grpc.CallOption) (*unitregistrypb.UnitResponse, error) {
	if err := f.record(ctx, "RegisterUnit"); err != nil {
		return nil, err
	}
	f.lastReg = in
	return &unitregistrypb.UnitResponse{Id: "u-" + in.GetSpec().GetToken(), Spec: in.GetSpec(), Status: "ACTIVE", Source: "manual", RegistryVersion: 2, CreatedBy: in.GetCreatedBy()}, nil
}

func (f *fakeRegistry) GetUnit(ctx context.Context, in *unitregistrypb.GetUnitRequest, _ ...grpc.CallOption) (*unitregistrypb.UnitResponse, error) {
	if err := f.record(ctx, "GetUnit"); err != nil {
		return nil, err
	}
	f.lastGet = in
	for _, u := range f.units {
		if (in.GetId() != "" && u.GetId() == in.GetId()) || (in.GetToken() != "" && u.GetSpec().GetToken() == in.GetToken()) {
			return u, nil
		}
	}
	return nil, status.Error(codes.NotFound, "unit '"+in.GetToken()+in.GetId()+"' not found")
}

func (f *fakeRegistry) ListUnits(context.Context, *unitregistrypb.ListUnitsRequest, ...grpc.CallOption) (*unitregistrypb.ListUnitsResponse, error) {
	return nil, errors.New("ListUnits is not used by the tools")
}

func (f *fakeRegistry) UpdateUnit(ctx context.Context, in *unitregistrypb.UpdateUnitRequest, _ ...grpc.CallOption) (*unitregistrypb.UnitResponse, error) {
	if err := f.record(ctx, "UpdateUnit"); err != nil {
		return nil, err
	}
	f.lastUpdate = in
	return &unitregistrypb.UnitResponse{Id: in.GetId(), Spec: in.GetSpec(), Status: "ACTIVE", Source: "manual", RegistryVersion: 3}, nil
}

func (f *fakeRegistry) DeleteUnit(ctx context.Context, in *unitregistrypb.DeleteUnitRequest, _ ...grpc.CallOption) (*unitregistrypb.DeleteUnitResponse, error) {
	if err := f.record(ctx, "DeleteUnit"); err != nil {
		return nil, err
	}
	f.lastDelete = in
	return &unitregistrypb.DeleteUnitResponse{Success: true}, nil
}

func (f *fakeRegistry) GetRegistryStatus(context.Context, *unitregistrypb.GetRegistryStatusRequest, ...grpc.CallOption) (*unitregistrypb.RegistryStatus, error) {
	return nil, errors.New("GetRegistryStatus is not used by the tools")
}

func (f *fakeRegistry) ValidateUnit(context.Context, *unitregistrypb.ValidateUnitRequest, ...grpc.CallOption) (*unitregistrypb.ValidationResult, error) {
	return nil, errors.New("ValidateUnit is not used by the tools")
}

func (f *fakeRegistry) CreateUnitType(ctx context.Context, in *unitregistrypb.CreateUnitTypeRequest, _ ...grpc.CallOption) (*unitregistrypb.UnitTypeResponse, error) {
	if err := f.record(ctx, "CreateUnitType"); err != nil {
		return nil, err
	}
	f.lastCreateT = in
	return &unitregistrypb.UnitTypeResponse{Id: "t-" + in.GetSpec().GetCode(), Spec: in.GetSpec(), IsActive: true}, nil
}

func (f *fakeRegistry) UpdateUnitType(ctx context.Context, in *unitregistrypb.UpdateUnitTypeRequest, _ ...grpc.CallOption) (*unitregistrypb.UnitTypeResponse, error) {
	if err := f.record(ctx, "UpdateUnitType"); err != nil {
		return nil, err
	}
	f.lastUpdateT = in
	return &unitregistrypb.UnitTypeResponse{Id: in.GetId(), Spec: in.GetSpec(), IsActive: true}, nil
}

func (f *fakeRegistry) DeactivateUnitType(ctx context.Context, in *unitregistrypb.DeactivateUnitTypeRequest, _ ...grpc.CallOption) (*unitregistrypb.UnitTypeResponse, error) {
	if err := f.record(ctx, "DeactivateUnitType"); err != nil {
		return nil, err
	}
	f.lastDeactT = in
	return &unitregistrypb.UnitTypeResponse{Id: in.GetId(), Spec: &unitregistrypb.UnitTypeSpec{Code: "CAPACITY"}, IsActive: false}, nil
}

func (f *fakeRegistry) GetUnitType(ctx context.Context, in *unitregistrypb.GetUnitTypeRequest, _ ...grpc.CallOption) (*unitregistrypb.UnitTypeResponse, error) {
	if err := f.record(ctx, "GetUnitType"); err != nil {
		return nil, err
	}
	f.lastGetT = in
	for _, t := range f.types {
		if (in.GetId() != "" && t.GetId() == in.GetId()) || (in.GetCode() != "" && t.GetSpec().GetCode() == in.GetCode()) {
			return t, nil
		}
	}
	return nil, status.Error(codes.NotFound, "type "+in.GetCode()+in.GetId()+" not found")
}

func (f *fakeRegistry) ListUnitTypes(ctx context.Context, _ *unitregistrypb.ListUnitTypesRequest, _ ...grpc.CallOption) (*unitregistrypb.ListUnitTypesResponse, error) {
	if err := f.record(ctx, "ListUnitTypes"); err != nil {
		return nil, err
	}
	out := &unitregistrypb.ListUnitTypesResponse{}
	for _, t := range f.types {
		out.Types = append(out.Types, t)
	}
	return out, nil
}

func (f *fakeRegistry) SetDimensionTypes(ctx context.Context, in *unitregistrypb.SetDimensionTypesRequest, _ ...grpc.CallOption) (*unitregistrypb.DimensionTypesResponse, error) {
	if err := f.record(ctx, "SetDimensionTypes"); err != nil {
		return nil, err
	}
	f.lastSetDims = in
	return &unitregistrypb.DimensionTypesResponse{Dimension: in.GetDimension(), TypeCodes: in.GetTypeCodes()}, nil
}

func callRegistry(t *testing.T, fake *fakeRegistry, tool string, args map[string]any) *mcp.CallToolResult {
	t.Helper()
	raw, err := json.Marshal(args)
	if err != nil {
		t.Fatalf("marshal args: %v", err)
	}
	var decoded map[string]any
	if err := json.Unmarshal(raw, &decoded); err != nil {
		t.Fatalf("unmarshal args: %v", err)
	}
	r := NewRegistry(&Clients{Normalization: &fakeNormalization{}, Units: fake, UnitsAdminKey: testAdminKey, Actor: "mcp:test"})
	return r.CallTool(context.Background(), &mcp.CallToolParams{Name: tool, Arguments: decoded})
}

func sampleArgs() map[string]any {
	return map[string]any{"label": "Poids", "value": 2, "expected_canonical_value": 50, "expected_canonical_unit": "kilogram"}
}

func TestCreateUnitForwardsEverythingWithTheBearer(t *testing.T) {
	fake := newFakeRegistry()
	res := callRegistry(t, fake, "create_unit", map[string]any{
		"token": "sac_ciment", "dimension": "mass", "pint_definition": "sac_ciment = 25 * kilogram",
		"aliases": []any{"sacs"}, "sample": sampleArgs(),
	})
	var out unitView
	decode(t, res, &out)
	if out.ID != "u-sac_ciment" || out.RegistryVersion != 2 || len(out.Types) != 0 {
		t.Fatalf("unexpected view: %+v", out)
	}
	spec := fake.lastReg.GetSpec()
	if spec.GetDimension() != "mass" || spec.GetAliases()[0] != "sacs" || fake.lastReg.GetCreatedBy() != "mcp:test" {
		t.Fatalf("unexpected request: %+v", fake.lastReg)
	}
	s := spec.GetRegressionSample()
	if s.GetValue() != "2" || s.GetExpectedCanonicalValue() != 50 || s.GetDataType() != "numeric" {
		t.Fatalf("unexpected sample: %+v", s)
	}
	if fake.auth["RegisterUnit"] != "Bearer "+testAdminKey {
		t.Fatalf("missing bearer: %q", fake.auth["RegisterUnit"])
	}
}

func TestCreateUnitAcceptsNumericStringsInSample(t *testing.T) {
	fake := newFakeRegistry()
	sample := map[string]any{"label": "Poids", "value": "2", "expected_canonical_value": "50", "expected_canonical_unit": "kilogram"}
	res := callRegistry(t, fake, "create_unit", map[string]any{"token": "sac", "dimension": "mass", "sample": sample})
	if res.IsError {
		t.Fatalf("unexpected error: %s", res.Content[0].Text)
	}
	if fake.lastReg.GetSpec().GetRegressionSample().GetExpectedCanonicalValue() != 50 {
		t.Fatalf("string number not parsed")
	}
}

func TestCreateUnitValidation(t *testing.T) {
	cases := []struct {
		name string
		args map[string]any
		want string
	}{
		{"no sample", map[string]any{"token": "sac", "dimension": "mass"}, "'sample' parameter is required"},
		{"no token", map[string]any{"dimension": "mass", "sample": sampleArgs()}, "'token'"},
		{"no dimension", map[string]any{"token": "sac", "sample": sampleArgs()}, "'dimension'"},
		{"bad aliases", map[string]any{"token": "sac", "dimension": "mass", "aliases": "sacs", "sample": sampleArgs()}, "'aliases' must be an array"},
		{"range without max", map[string]any{"token": "sac", "dimension": "mass", "sample": map[string]any{
			"label": "Poids", "value": 1, "data_type": "numeric_range", "expected_canonical_value": 25, "expected_canonical_unit": "kilogram"}}, "value_max"},
		{"bad data_type", map[string]any{"token": "sac", "dimension": "mass", "sample": map[string]any{
			"label": "Poids", "value": 1, "data_type": "text", "expected_canonical_value": 25, "expected_canonical_unit": "kilogram"}}, "data_type"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			fake := newFakeRegistry()
			wantError(t, callRegistry(t, fake, "create_unit", tc.args), tc.want)
			if len(fake.calls) != 0 {
				t.Fatalf("backend called despite invalid input: %v", fake.calls)
			}
		})
	}
}

func TestServerValidationErrorsPassThrough(t *testing.T) {
	fake := newFakeRegistry()
	fake.err = status.Error(codes.InvalidArgument, "G1: pint cannot evaluate 'x = 3 * nope'")
	wantError(t, callRegistry(t, fake, "create_unit", map[string]any{"token": "x", "dimension": "mass", "sample": sampleArgs()}), "G1: pint cannot evaluate")
}

func TestUnauthenticatedAndUnavailableErrors(t *testing.T) {
	fake := newFakeRegistry()
	fake.err = status.Error(codes.Unauthenticated, "missing or invalid admin bearer")
	wantError(t, callRegistry(t, fake, "deactivate_unit", map[string]any{"id": "u-kg"}), "UNITS_ADMIN_KEY")
	fake.err = status.Error(codes.Unavailable, "connection refused")
	wantError(t, callRegistry(t, fake, "get_unit", map[string]any{"id": "u-kg"}), "unit registry unavailable")
}

func TestUpdateUnitByTokenSendsOnlyTheGivenFields(t *testing.T) {
	fake := newFakeRegistry()
	res := callRegistry(t, fake, "update_unit", map[string]any{"token": "kg", "aliases": []any{}})
	if res.IsError {
		t.Fatalf("unexpected error: %s", res.Content[0].Text)
	}
	if fake.lastGet.GetToken() != "kg" || fake.auth["GetUnit"] != "" {
		t.Fatalf("token lookup must be an unauthenticated read: %+v auth=%q", fake.lastGet, fake.auth["GetUnit"])
	}
	if fake.lastUpdate.GetId() != "u-kg" || len(fake.lastUpdate.GetSpec().GetAliases()) != 0 {
		t.Fatalf("unexpected update: %+v", fake.lastUpdate)
	}
	if paths := fake.lastUpdate.GetUpdateMask().GetPaths(); len(paths) != 1 || paths[0] != "aliases" {
		t.Fatalf("mask = %v", paths)
	}
	if fake.auth["UpdateUnit"] != "Bearer "+testAdminKey {
		t.Fatalf("missing bearer on UpdateUnit")
	}
}

func TestUpdateUnitSampleMapsToRegressionSamplePath(t *testing.T) {
	fake := newFakeRegistry()
	callRegistry(t, fake, "update_unit", map[string]any{"id": "u-kg", "dimension": "mass", "sample": sampleArgs()})
	paths := fake.lastUpdate.GetUpdateMask().GetPaths()
	if len(paths) != 2 || paths[0] != "dimension" || paths[1] != "regression_sample" {
		t.Fatalf("mask = %v", paths)
	}
}

func TestUpdateUnitValidation(t *testing.T) {
	fake := newFakeRegistry()
	wantError(t, callRegistry(t, fake, "update_unit", map[string]any{"id": "u-kg"}), "nothing to update")
	wantError(t, callRegistry(t, fake, "update_unit", map[string]any{"id": "u-kg", "token": "kg", "aliases": []any{}}), "either 'id' or 'token'")
	wantError(t, callRegistry(t, fake, "update_unit", map[string]any{"aliases": []any{}}), "'id' or 'token' is required")
	wantError(t, callRegistry(t, fake, "update_unit", map[string]any{"token": "nope", "aliases": []any{}}), "not found")
}

func TestDeactivateUnitById(t *testing.T) {
	fake := newFakeRegistry()
	res := callRegistry(t, fake, "deactivate_unit", map[string]any{"id": "u-kg"})
	var out map[string]any
	decode(t, res, &out)
	if out["id"] != "u-kg" || out["status"] != "DISABLED" {
		t.Fatalf("unexpected output: %v", out)
	}
	if fake.lastDelete.GetId() != "u-kg" || fake.lastDelete.GetDeletedBy() != "mcp:test" || fake.auth["DeleteUnit"] == "" {
		t.Fatalf("unexpected delete: %+v auth=%q", fake.lastDelete, fake.auth["DeleteUnit"])
	}
}

func TestGetUnitByTokenIsAnOpenRead(t *testing.T) {
	fake := newFakeRegistry()
	var out unitView
	decode(t, callRegistry(t, fake, "get_unit", map[string]any{"token": "kg"}), &out)
	if out.ID != "u-kg" || out.Types[0] != "CAPACITY" || fake.auth["GetUnit"] != "" {
		t.Fatalf("unexpected: %+v auth=%q", out, fake.auth["GetUnit"])
	}
	wantError(t, callRegistry(t, fake, "get_unit", map[string]any{"token": "nope"}), "not found")
}
```

- [ ] **Step 5: Run the tests to verify they fail**

Run: `scripts/mcp-normalize-test.sh`
Expected: compile errors such as `undefined: createUnitDescription`, `undefined: unitView`.

- [ ] **Step 6: Write `units.go`**

`internal/tools/units.go`:

```go
package tools

import (
	"context"
	"fmt"
	"log"
	"strings"
	"time"

	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/metadata"
	"google.golang.org/grpc/status"
	"google.golang.org/protobuf/types/known/fieldmaskpb"

	"github.com/hellopro/mcp-normalize-unite/internal/mcp"
	unitregistrypb "github.com/hellopro/mcp-normalize-unite/proto/gen/unit_registry"
)

// registryTimeout bounds each unit-registry call: a write runs six guards and rebuilds
// a pint registry (about a second); a read is a single DB query.
const registryTimeout = 15 * time.Second

const sampleSchema = `{
	"type": "object",
	"description": "Exemple obligatoire, rejoué à chaque modification de l'unité (test de non-régression permanent).",
	"properties": {
		"label": {"type": "string", "description": "Libellé de caractéristique (ex. 'Poids')."},
		"value": {"type": ["string", "number"], "description": "Valeur brute (ex. 2)."},
		"unit": {"type": "string", "description": "Unité à normaliser ; par défaut le token de l'unité."},
		"data_type": {"type": "string", "enum": ["numeric", "numeric_range"], "description": "Défaut : 'numeric'."},
		"value_max": {"type": ["string", "number"], "description": "Borne haute, obligatoire si data_type = 'numeric_range'."},
		"expected_canonical_value": {"type": ["number", "string"], "description": "Valeur canonique attendue (ex. 50)."},
		"expected_canonical_max": {"type": ["number", "string"], "description": "Borne haute canonique attendue (numeric_range)."},
		"expected_canonical_unit": {"type": "string", "description": "Unité canonique attendue, telle que renvoyée par normalize_quantity (ex. 'kilogram')."}
	},
	"required": ["label", "value", "expected_canonical_value", "expected_canonical_unit"]
}`

const createUnitDescription = "Créer une unité de normalisation dans le registre HelloPro (unit-registry-service). " +
	"Elle est active sur tous les réplicas du normaliseur en environ une seconde. Six garde-fous (G1–G6) valident " +
	"la définition pint, la dimension, les collisions de noms et rejouent l'exemple 'sample', obligatoire car il " +
	"devient un test permanent. Si un token désactivé existe déjà, il est réactivé avec les nouvelles valeurs."

const createUnitInputSchema = `{
	"type": "object",
	"properties": {
		"token": {"type": "string", "description": "Unité telle qu'elle apparaît dans les fiches (ex. 'sac', 'galettes'). Comparée en minuscules."},
		"dimension": {"type": "string", "description": "Dimension physique existante (ex. 'mass', 'length', 'volume', 'count'). Utiliser get_unit sur une unité proche pour voir le nom exact."},
		"pint_definition": {"type": "string", "description": "Définition pint si pint ne connaît pas l'unité : '<nom> = <expression> [= alias ...]' (ex. 'sac_ciment = 25 * kilogram'). À omettre si pint la connaît."},
		"aliases": {"type": "array", "items": {"type": "string"}, "description": "Autres graphies à reconnaître (ex. ['sacs'])."},
		"depends_on": {"type": "array", "items": {"type": "string"}, "description": "Unités personnalisées utilisées dans pint_definition."},
		"sample": ` + sampleSchema + `
	},
	"required": ["token", "dimension", "sample"]
}`

const updateUnitDescription = "Modifier une unité existante (par 'id' ou 'token'). Seuls les champs fournis changent ; " +
	"'aliases': [] vide la liste. Les six garde-fous sont rejoués : une unité issue du seed n'a pas d'exemple, " +
	"il faut donc fournir 'sample' pour la modifier. Effet sur tous les réplicas en environ une seconde."

const updateUnitInputSchema = `{
	"type": "object",
	"properties": {
		"id": {"type": "string", "description": "Identifiant de l'unité (ou utiliser 'token')."},
		"token": {"type": "string", "description": "Token exact de l'unité (ou utiliser 'id')."},
		"dimension": {"type": "string", "description": "Nouvelle dimension physique."},
		"pint_definition": {"type": "string", "description": "Nouvelle définition pint ; chaîne vide pour la retirer."},
		"aliases": {"type": "array", "items": {"type": "string"}, "description": "Remplace la liste des graphies ([] la vide)."},
		"depends_on": {"type": "array", "items": {"type": "string"}, "description": "Remplace la liste des dépendances."},
		"sample": ` + sampleSchema + `
	}
}`

const deactivateUnitDescription = "Désactiver une unité (par 'id' ou 'token') : elle n'est plus reconnue par le normaliseur " +
	"en environ une seconde. Refusé si d'autres unités en dépendent (le message les liste). Recréer le même token " +
	"avec create_unit la réactive."

const getUnitDescription = "Lire une unité du registre (par 'id' ou 'token') : définition pint, dimension, graphies, " +
	"statut, exemple de non-régression et types hérités de sa dimension (ex. DIMENSION, CAPACITY)."

const unitRefInputSchema = `{
	"type": "object",
	"properties": {
		"id": {"type": "string", "description": "Identifiant de l'unité."},
		"token": {"type": "string", "description": "Token exact de l'unité (sensible à la casse et aux accents)."}
	}
}`

type sampleView struct {
	Label                  string   `json:"label"`
	Unit                   string   `json:"unit,omitempty"`
	Value                  string   `json:"value"`
	ValueMax               *string  `json:"value_max,omitempty"`
	DataType               string   `json:"data_type"`
	ExpectedCanonicalValue float64  `json:"expected_canonical_value"`
	ExpectedCanonicalMax   *float64 `json:"expected_canonical_max,omitempty"`
	ExpectedCanonicalUnit  string   `json:"expected_canonical_unit"`
}

type unitView struct {
	ID              string      `json:"id"`
	Token           string      `json:"token"`
	Dimension       string      `json:"dimension,omitempty"`
	Types           []string    `json:"types"`
	PintDefinition  string      `json:"pint_definition,omitempty"`
	Aliases         []string    `json:"aliases"`
	DependsOn       []string    `json:"depends_on"`
	Status          string      `json:"status"`
	Source          string      `json:"source"`
	Sample          *sampleView `json:"sample,omitempty"`
	RegistryVersion int64       `json:"registry_version,omitempty"`
	CreatedBy       string      `json:"created_by,omitempty"`
	CreatedAt       string      `json:"created_at,omitempty"`
	UpdatedAt       string      `json:"updated_at,omitempty"`
}

func orEmpty(s []string) []string {
	if s == nil {
		return []string{}
	}
	return s
}

func toUnitView(u *unitregistrypb.UnitResponse) unitView {
	spec := u.GetSpec()
	view := unitView{
		ID: u.GetId(), Token: spec.GetToken(), Dimension: spec.GetDimension(), Types: orEmpty(u.GetTypes()),
		PintDefinition: spec.GetPintDefinition(), Aliases: orEmpty(spec.GetAliases()), DependsOn: orEmpty(spec.GetDependsOn()),
		Status: u.GetStatus(), Source: u.GetSource(), RegistryVersion: u.GetRegistryVersion(),
		CreatedBy: u.GetCreatedBy(), CreatedAt: u.GetCreatedAt(), UpdatedAt: u.GetUpdatedAt(),
	}
	if s := spec.GetRegressionSample(); s != nil {
		view.Sample = &sampleView{
			Label: s.GetLabel(), Unit: s.GetUnit(), Value: s.GetValue(), ValueMax: s.ValueMax, DataType: s.GetDataType(),
			ExpectedCanonicalValue: s.GetExpectedCanonicalValue(), ExpectedCanonicalMax: s.ExpectedCanonicalMax,
			ExpectedCanonicalUnit: s.GetExpectedCanonicalUnit(),
		}
	}
	return view
}

func registryCtx(ctx context.Context, clients *Clients, write bool) (context.Context, context.CancelFunc) {
	ctx, cancel := context.WithTimeout(ctx, registryTimeout)
	if write {
		ctx = metadata.AppendToOutgoingContext(ctx, "authorization", "Bearer "+clients.UnitsAdminKey)
	}
	return ctx, cancel
}

// registryError turns a unit-registry gRPC error into a tool error the agent can act on.
func registryError(op string, err error) *mcp.CallToolResult {
	if st, ok := status.FromError(err); ok {
		switch st.Code() {
		case codes.InvalidArgument, codes.AlreadyExists, codes.NotFound, codes.FailedPrecondition:
			return errorResult(st.Message())
		case codes.Unauthenticated:
			log.Printf("[tools] %s: unit registry rejected UNITS_ADMIN_KEY", op)
			return errorResult("unit registry rejected this MCP server's admin key (check UNITS_ADMIN_KEY)")
		}
	}
	log.Printf("[tools] %s failed: %v", op, err)
	return errorResult(fmt.Sprintf("unit registry unavailable: %v", err))
}

// stringList reads an optional array of non-empty strings; present reports whether the key was given.
func stringList(args map[string]any, key string) (list []string, present bool, errRes *mcp.CallToolResult) {
	raw, ok := args[key]
	if !ok || raw == nil {
		return nil, false, nil
	}
	items, ok := raw.([]any)
	if !ok {
		return nil, true, errorResult(fmt.Sprintf("'%s' must be an array of strings", key))
	}
	out := make([]string, 0, len(items))
	for _, item := range items {
		s, ok := item.(string)
		if !ok || strings.TrimSpace(s) == "" {
			return nil, true, errorResult(fmt.Sprintf("'%s' must contain non-empty strings", key))
		}
		out = append(out, strings.TrimSpace(s))
	}
	return out, true, nil
}

func prefixed(errRes *mcp.CallToolResult) *mcp.CallToolResult {
	return errorResult("sample: " + errRes.Content[0].Text)
}

// parseSample reads the optional 'sample' object; present reports whether the key was given.
func parseSample(args map[string]any) (*unitregistrypb.RegressionSample, bool, *mcp.CallToolResult) {
	raw, ok := args["sample"]
	if !ok || raw == nil {
		return nil, false, nil
	}
	obj, ok := raw.(map[string]any)
	if !ok {
		return nil, true, errorResult("'sample' must be an object")
	}
	label, errRes := requiredString(obj, "label")
	if errRes != nil {
		return nil, true, prefixed(errRes)
	}
	value, errRes := quantityValue(obj)
	if errRes != nil {
		return nil, true, prefixed(errRes)
	}
	unit, errRes := optionalString(obj, "unit")
	if errRes != nil {
		return nil, true, prefixed(errRes)
	}
	dataType, errRes := optionalString(obj, "data_type")
	if errRes != nil {
		return nil, true, prefixed(errRes)
	}
	if dataType == "" {
		dataType = "numeric"
	}
	if !contains(allowedDataTypes, dataType) {
		return nil, true, errorResult(fmt.Sprintf("sample: 'data_type' must be one of %v", allowedDataTypes))
	}
	expected, errRes := optionalNumber(obj, "expected_canonical_value")
	if errRes != nil {
		return nil, true, prefixed(errRes)
	}
	if expected == nil {
		return nil, true, errorResult("sample: 'expected_canonical_value' parameter is required")
	}
	expectedUnit, errRes := requiredString(obj, "expected_canonical_unit")
	if errRes != nil {
		return nil, true, prefixed(errRes)
	}
	sample := &unitregistrypb.RegressionSample{
		Label: label, Unit: unit, Value: value, DataType: dataType,
		ExpectedCanonicalValue: *expected, ExpectedCanonicalUnit: expectedUnit,
	}
	valueMax, errRes := optionalNumber(obj, "value_max")
	if errRes != nil {
		return nil, true, prefixed(errRes)
	}
	if valueMax != nil {
		formatted := formatNumber(*valueMax)
		sample.ValueMax = &formatted
	}
	expectedMax, errRes := optionalNumber(obj, "expected_canonical_max")
	if errRes != nil {
		return nil, true, prefixed(errRes)
	}
	sample.ExpectedCanonicalMax = expectedMax
	if dataType == "numeric_range" && sample.ValueMax == nil {
		return nil, true, errorResult("sample: 'value_max' is required when data_type is 'numeric_range'")
	}
	return sample, true, nil
}

// resolveUnitID returns the id given directly, or looks the token up with an open read.
func resolveUnitID(ctx context.Context, clients *Clients, args map[string]any) (string, *mcp.CallToolResult) {
	id, errRes := optionalString(args, "id")
	if errRes != nil {
		return "", errRes
	}
	token, errRes := optionalString(args, "token")
	if errRes != nil {
		return "", errRes
	}
	switch {
	case id != "" && token != "":
		return "", errorResult("give either 'id' or 'token', not both")
	case id != "":
		return id, nil
	case token == "":
		return "", errorResult("'id' or 'token' is required")
	}
	callCtx, cancel := registryCtx(ctx, clients, false)
	defer cancel()
	unit, err := clients.Units.GetUnit(callCtx, &unitregistrypb.GetUnitRequest{Token: token})
	if err != nil {
		return "", registryError("get_unit", err)
	}
	return unit.GetId(), nil
}

func handleCreateUnit(ctx context.Context, clients *Clients, args map[string]any) (*mcp.CallToolResult, error) {
	token, errRes := requiredString(args, "token")
	if errRes != nil {
		return errRes, nil
	}
	dimension, errRes := requiredString(args, "dimension")
	if errRes != nil {
		return errRes, nil
	}
	definition, errRes := optionalString(args, "pint_definition")
	if errRes != nil {
		return errRes, nil
	}
	aliases, _, errRes := stringList(args, "aliases")
	if errRes != nil {
		return errRes, nil
	}
	dependsOn, _, errRes := stringList(args, "depends_on")
	if errRes != nil {
		return errRes, nil
	}
	sample, present, errRes := parseSample(args)
	if errRes != nil {
		return errRes, nil
	}
	if !present {
		return errorResult("'sample' parameter is required: it becomes the unit's permanent regression test"), nil
	}
	callCtx, cancel := registryCtx(ctx, clients, true)
	defer cancel()
	unit, err := clients.Units.RegisterUnit(callCtx, &unitregistrypb.RegisterUnitRequest{
		Spec: &unitregistrypb.UnitSpec{Token: token, Dimension: dimension, PintDefinition: definition,
			Aliases: aliases, DependsOn: dependsOn, RegressionSample: sample},
		CreatedBy: clients.Actor,
	})
	if err != nil {
		return registryError("create_unit", err), nil
	}
	return jsonResult(toUnitView(unit)), nil
}

func handleUpdateUnit(ctx context.Context, clients *Clients, args map[string]any) (*mcp.CallToolResult, error) {
	spec := &unitregistrypb.UnitSpec{}
	var paths []string
	if raw, ok := args["dimension"]; ok && raw != nil {
		dimension, errRes := requiredString(args, "dimension")
		if errRes != nil {
			return errRes, nil
		}
		spec.Dimension = dimension
		paths = append(paths, "dimension")
	}
	if _, ok := args["pint_definition"]; ok {
		definition, errRes := optionalString(args, "pint_definition")
		if errRes != nil {
			return errRes, nil
		}
		spec.PintDefinition = definition // "" clears it
		paths = append(paths, "pint_definition")
	}
	aliases, present, errRes := stringList(args, "aliases")
	if errRes != nil {
		return errRes, nil
	}
	if present {
		spec.Aliases = aliases
		paths = append(paths, "aliases")
	}
	dependsOn, present, errRes := stringList(args, "depends_on")
	if errRes != nil {
		return errRes, nil
	}
	if present {
		spec.DependsOn = dependsOn
		paths = append(paths, "depends_on")
	}
	sample, present, errRes := parseSample(args)
	if errRes != nil {
		return errRes, nil
	}
	if present {
		spec.RegressionSample = sample
		paths = append(paths, "regression_sample")
	}
	if len(paths) == 0 {
		return errorResult("nothing to update: give at least one of dimension, pint_definition, aliases, depends_on, sample"), nil
	}
	id, errRes := resolveUnitID(ctx, clients, args)
	if errRes != nil {
		return errRes, nil
	}
	callCtx, cancel := registryCtx(ctx, clients, true)
	defer cancel()
	unit, err := clients.Units.UpdateUnit(callCtx, &unitregistrypb.UpdateUnitRequest{
		Id: id, Spec: spec, UpdateMask: &fieldmaskpb.FieldMask{Paths: paths}, UpdatedBy: clients.Actor,
	})
	if err != nil {
		return registryError("update_unit", err), nil
	}
	return jsonResult(toUnitView(unit)), nil
}

func handleDeactivateUnit(ctx context.Context, clients *Clients, args map[string]any) (*mcp.CallToolResult, error) {
	id, errRes := resolveUnitID(ctx, clients, args)
	if errRes != nil {
		return errRes, nil
	}
	callCtx, cancel := registryCtx(ctx, clients, true)
	defer cancel()
	if _, err := clients.Units.DeleteUnit(callCtx, &unitregistrypb.DeleteUnitRequest{Id: id, DeletedBy: clients.Actor}); err != nil {
		return registryError("deactivate_unit", err), nil
	}
	return jsonResult(map[string]string{"id": id, "status": "DISABLED"}), nil
}

func handleGetUnit(ctx context.Context, clients *Clients, args map[string]any) (*mcp.CallToolResult, error) {
	id, errRes := optionalString(args, "id")
	if errRes != nil {
		return errRes, nil
	}
	token, errRes := optionalString(args, "token")
	if errRes != nil {
		return errRes, nil
	}
	if (id == "") == (token == "") {
		return errorResult("give exactly one of 'id' or 'token'"), nil
	}
	callCtx, cancel := registryCtx(ctx, clients, false)
	defer cancel()
	unit, err := clients.Units.GetUnit(callCtx, &unitregistrypb.GetUnitRequest{Id: id, Token: token})
	if err != nil {
		return registryError("get_unit", err), nil
	}
	return jsonResult(toUnitView(unit)), nil
}
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `scripts/mcp-normalize-test.sh`
Expected: `ok  github.com/hellopro/mcp-normalize-unite/internal/tools`, with no vet findings.

- [ ] **Step 8: Commit**

```bash
git add scripts/mcp-normalize-test.sh apps-microservices/mcp-normalize-unite-service
git commit -m "feat(mcp-normalize-unite-service): create/update/deactivate/get unit tools" -m "EN: Four MCP tools on unit-registry-service over gRPC; writes carry Bearer UNITS_ADMIN_KEY, token lookups are open reads, update sends a FieldMask of exactly the fields given, and guard messages are returned verbatim so the agent can fix its input." -m "FR : Quatre outils MCP sur unit-registry-service en gRPC ; les ecritures portent Bearer UNITS_ADMIN_KEY, les recherches par token sont des lectures ouvertes, update envoie un FieldMask des seuls champs fournis, et les messages des garde-fous sont renvoyes tels quels pour que l'agent corrige sa saisie."
```

---

### Task 15: MCP — the 5 unit-type tools + docs

**Files:**
- Create: `apps-microservices/mcp-normalize-unite-service/internal/tools/unit_types.go`, `internal/tools/unit_types_test.go`
- Modify: `internal/tools/registry.go` (5 registrations), `internal/tools/normalize_test.go` (`TestToolsList`), `apps-microservices/mcp-normalize-unite-service/CLAUDE.md`

**Interfaces:**
- Consumes: `fakeRegistry`, `newFakeRegistry`, `callRegistry`, `testAdminKey`, `registryCtx`, `registryError`, `stringList`, `orEmpty` (Task 14).
- Produces: tools `create_unit_type`, `update_unit_type`, `deactivate_unit_type`, `get_unit_type`, `set_dimension_types`.

- [ ] **Step 1: Write the failing tests**

In `TestToolsList`, change the expected string to:

```go
	if strings.Join(names, ",") != "normalize_quantity,normalize_range,create_unit,update_unit,deactivate_unit,get_unit,create_unit_type,update_unit_type,deactivate_unit_type,get_unit_type,set_dimension_types" {
```

`internal/tools/unit_types_test.go`:

```go
package tools

import (
	"testing"

	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

func TestCreateUnitTypeForwardsWithTheBearer(t *testing.T) {
	fake := newFakeRegistry()
	var out unitTypeView
	decode(t, callRegistry(t, fake, "create_unit_type", map[string]any{"code": "POIDS", "label": "Poids", "description": "Masse"}), &out)
	if out.Code != "POIDS" || !out.IsActive || len(out.Dimensions) != 0 {
		t.Fatalf("unexpected view: %+v", out)
	}
	spec := fake.lastCreateT.GetSpec()
	if spec.GetLabel() != "Poids" || spec.GetDescription() != "Masse" || fake.lastCreateT.GetCreatedBy() != "mcp:test" {
		t.Fatalf("unexpected request: %+v", fake.lastCreateT)
	}
	if fake.auth["CreateUnitType"] != "Bearer "+testAdminKey {
		t.Fatalf("missing bearer")
	}
}

func TestCreateUnitTypeValidation(t *testing.T) {
	fake := newFakeRegistry()
	wantError(t, callRegistry(t, fake, "create_unit_type", map[string]any{"label": "Poids"}), "'code'")
	wantError(t, callRegistry(t, fake, "create_unit_type", map[string]any{"code": "POIDS"}), "'label'")
	if len(fake.calls) != 0 {
		t.Fatalf("backend called: %v", fake.calls)
	}
}

func TestGetUnitTypeListsWhenNoReferenceIsGiven(t *testing.T) {
	fake := newFakeRegistry()
	var out []unitTypeView
	decode(t, callRegistry(t, fake, "get_unit_type", map[string]any{}), &out)
	if len(out) != 1 || out[0].Code != "CAPACITY" || fake.calls[0] != "ListUnitTypes" {
		t.Fatalf("unexpected: %+v calls=%v", out, fake.calls)
	}
	var one unitTypeView
	decode(t, callRegistry(t, fake, "get_unit_type", map[string]any{"code": "CAPACITY"}), &one)
	if one.ID != "t-cap" || fake.lastGetT.GetCode() != "CAPACITY" || fake.auth["GetUnitType"] != "" {
		t.Fatalf("unexpected: %+v", one)
	}
}

func TestUpdateUnitTypeByCodeSendsALabelMask(t *testing.T) {
	fake := newFakeRegistry()
	res := callRegistry(t, fake, "update_unit_type", map[string]any{"code": "CAPACITY", "label": "Contenance"})
	if res.IsError {
		t.Fatalf("unexpected error: %s", res.Content[0].Text)
	}
	if fake.lastUpdateT.GetId() != "t-cap" || fake.lastUpdateT.GetSpec().GetLabel() != "Contenance" {
		t.Fatalf("unexpected update: %+v", fake.lastUpdateT)
	}
	if paths := fake.lastUpdateT.GetUpdateMask().GetPaths(); len(paths) != 1 || paths[0] != "label" {
		t.Fatalf("mask = %v", paths)
	}
	wantError(t, callRegistry(t, fake, "update_unit_type", map[string]any{"code": "CAPACITY"}), "nothing to update")
}

func TestDeactivateUnitTypeById(t *testing.T) {
	fake := newFakeRegistry()
	var out unitTypeView
	decode(t, callRegistry(t, fake, "deactivate_unit_type", map[string]any{"id": "t-cap"}), &out)
	if out.IsActive || fake.lastDeactT.GetId() != "t-cap" || fake.auth["DeactivateUnitType"] == "" {
		t.Fatalf("unexpected: %+v", out)
	}
}

func TestSetDimensionTypesAllowsAnEmptyListToClear(t *testing.T) {
	fake := newFakeRegistry()
	var out map[string]any
	decode(t, callRegistry(t, fake, "set_dimension_types", map[string]any{"dimension": "volume", "type_codes": []any{}}), &out)
	if fake.lastSetDims.GetDimension() != "volume" || len(fake.lastSetDims.GetTypeCodes()) != 0 {
		t.Fatalf("unexpected request: %+v", fake.lastSetDims)
	}
	if codes, ok := out["type_codes"].([]any); !ok || len(codes) != 0 {
		t.Fatalf("type_codes must be an empty array, got %v", out["type_codes"])
	}
	wantError(t, callRegistry(t, fake, "set_dimension_types", map[string]any{"dimension": "volume"}), "'type_codes' parameter is required")
}

func TestUnitTypeServerErrorsPassThrough(t *testing.T) {
	fake := newFakeRegistry()
	fake.err = status.Error(codes.FailedPrecondition, "type CAPACITY is inactive")
	wantError(t, callRegistry(t, fake, "set_dimension_types", map[string]any{"dimension": "volume", "type_codes": []any{"CAPACITY"}}), "is inactive")
}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `scripts/mcp-normalize-test.sh`
Expected: compile error `undefined: unitTypeView`.

- [ ] **Step 3: Write `unit_types.go` and register the tools**

`internal/tools/unit_types.go`:

```go
package tools

import (
	"context"
	"sort"

	"google.golang.org/protobuf/types/known/fieldmaskpb"

	"github.com/hellopro/mcp-normalize-unite/internal/mcp"
	unitregistrypb "github.com/hellopro/mcp-normalize-unite/proto/gen/unit_registry"
)

const createUnitTypeDescription = "Créer un type d'unité (catégorie métier, ex. DIMENSION, CAPACITY). Appeler d'abord " +
	"get_unit_type sans argument pour réutiliser un type existant : un code trop proche d'un type existant est refusé. " +
	"Code en MAJUSCULES (lettres, chiffres, _), immuable. Recréer un code désactivé le réactive. Un type ne change pas la normalisation."

const createUnitTypeInputSchema = `{
	"type": "object",
	"properties": {
		"code": {"type": "string", "description": "Code stable en MAJUSCULES, ex. 'CAPACITY'."},
		"label": {"type": "string", "description": "Libellé affiché, ex. 'Capacité'."},
		"description": {"type": "string", "description": "Description facultative."}
	},
	"required": ["code", "label"]
}`

const updateUnitTypeDescription = "Modifier le libellé ou la description d'un type d'unité (par 'id' ou 'code'). Le code est immuable."

const updateUnitTypeInputSchema = `{
	"type": "object",
	"properties": {
		"id": {"type": "string"},
		"code": {"type": "string", "description": "Code du type à modifier (ou utiliser 'id')."},
		"label": {"type": "string"},
		"description": {"type": "string"}
	}
}`

const deactivateUnitTypeDescription = "Désactiver un type d'unité (par 'id' ou 'code') : il n'apparaît plus sur les unités, " +
	"mais ses liens aux dimensions sont conservés et reviennent si on le recrée avec create_unit_type."

const getUnitTypeDescription = "Lire un type d'unité (par 'id' ou 'code') avec les dimensions qui lui sont liées, " +
	"ou, sans argument, lister tous les types actifs."

const unitTypeRefInputSchema = `{
	"type": "object",
	"properties": {
		"id": {"type": "string"},
		"code": {"type": "string", "description": "Code du type, ex. 'CAPACITY'."}
	}
}`

const setDimensionTypesDescription = "Définir les types d'une dimension physique (ex. 'length' -> ['DIMENSION']). " +
	"Remplace l'ensemble existant ; [] le vide. Toutes les unités de cette dimension héritent de ces types. " +
	"Chaque code doit exister et être actif (créer les nouveaux avec create_unit_type)."

const setDimensionTypesInputSchema = `{
	"type": "object",
	"properties": {
		"dimension": {"type": "string", "description": "Nom exact de la dimension (ex. 'length', 'volume', 'mass')."},
		"type_codes": {"type": "array", "items": {"type": "string"}, "description": "Codes de types, ex. ['CAPACITY']."}
	},
	"required": ["dimension", "type_codes"]
}`

type unitTypeView struct {
	ID          string   `json:"id"`
	Code        string   `json:"code"`
	Label       string   `json:"label"`
	Description string   `json:"description,omitempty"`
	IsActive    bool     `json:"is_active"`
	Dimensions  []string `json:"dimensions"`
	CreatedBy   string   `json:"created_by,omitempty"`
	CreatedAt   string   `json:"created_at,omitempty"`
	UpdatedAt   string   `json:"updated_at,omitempty"`
}

func toUnitTypeView(t *unitregistrypb.UnitTypeResponse) unitTypeView {
	return unitTypeView{
		ID: t.GetId(), Code: t.GetSpec().GetCode(), Label: t.GetSpec().GetLabel(), Description: t.GetSpec().GetDescription(),
		IsActive: t.GetIsActive(), Dimensions: orEmpty(t.GetDimensions()),
		CreatedBy: t.GetCreatedBy(), CreatedAt: t.GetCreatedAt(), UpdatedAt: t.GetUpdatedAt(),
	}
}

// resolveTypeID returns the id given directly, or looks the code up with an open read.
func resolveTypeID(ctx context.Context, clients *Clients, args map[string]any) (string, *mcp.CallToolResult) {
	id, errRes := optionalString(args, "id")
	if errRes != nil {
		return "", errRes
	}
	code, errRes := optionalString(args, "code")
	if errRes != nil {
		return "", errRes
	}
	switch {
	case id != "" && code != "":
		return "", errorResult("give either 'id' or 'code', not both")
	case id != "":
		return id, nil
	case code == "":
		return "", errorResult("'id' or 'code' is required")
	}
	callCtx, cancel := registryCtx(ctx, clients, false)
	defer cancel()
	found, err := clients.Units.GetUnitType(callCtx, &unitregistrypb.GetUnitTypeRequest{Code: code})
	if err != nil {
		return "", registryError("get_unit_type", err)
	}
	return found.GetId(), nil
}

func handleCreateUnitType(ctx context.Context, clients *Clients, args map[string]any) (*mcp.CallToolResult, error) {
	code, errRes := requiredString(args, "code")
	if errRes != nil {
		return errRes, nil
	}
	label, errRes := requiredString(args, "label")
	if errRes != nil {
		return errRes, nil
	}
	description, errRes := optionalString(args, "description")
	if errRes != nil {
		return errRes, nil
	}
	callCtx, cancel := registryCtx(ctx, clients, true)
	defer cancel()
	created, err := clients.Units.CreateUnitType(callCtx, &unitregistrypb.CreateUnitTypeRequest{
		Spec: &unitregistrypb.UnitTypeSpec{Code: code, Label: label, Description: description}, CreatedBy: clients.Actor,
	})
	if err != nil {
		return registryError("create_unit_type", err), nil
	}
	return jsonResult(toUnitTypeView(created)), nil
}

func handleUpdateUnitType(ctx context.Context, clients *Clients, args map[string]any) (*mcp.CallToolResult, error) {
	spec := &unitregistrypb.UnitTypeSpec{}
	var paths []string
	if raw, ok := args["label"]; ok && raw != nil {
		label, errRes := requiredString(args, "label")
		if errRes != nil {
			return errRes, nil
		}
		spec.Label = label
		paths = append(paths, "label")
	}
	if _, ok := args["description"]; ok {
		description, errRes := optionalString(args, "description")
		if errRes != nil {
			return errRes, nil
		}
		spec.Description = description
		paths = append(paths, "description")
	}
	if len(paths) == 0 {
		return errorResult("nothing to update: give 'label' and/or 'description'"), nil
	}
	id, errRes := resolveTypeID(ctx, clients, args)
	if errRes != nil {
		return errRes, nil
	}
	callCtx, cancel := registryCtx(ctx, clients, true)
	defer cancel()
	updated, err := clients.Units.UpdateUnitType(callCtx, &unitregistrypb.UpdateUnitTypeRequest{
		Id: id, Spec: spec, UpdateMask: &fieldmaskpb.FieldMask{Paths: paths}, UpdatedBy: clients.Actor,
	})
	if err != nil {
		return registryError("update_unit_type", err), nil
	}
	return jsonResult(toUnitTypeView(updated)), nil
}

func handleDeactivateUnitType(ctx context.Context, clients *Clients, args map[string]any) (*mcp.CallToolResult, error) {
	id, errRes := resolveTypeID(ctx, clients, args)
	if errRes != nil {
		return errRes, nil
	}
	callCtx, cancel := registryCtx(ctx, clients, true)
	defer cancel()
	deactivated, err := clients.Units.DeactivateUnitType(callCtx, &unitregistrypb.DeactivateUnitTypeRequest{Id: id, UpdatedBy: clients.Actor})
	if err != nil {
		return registryError("deactivate_unit_type", err), nil
	}
	return jsonResult(toUnitTypeView(deactivated)), nil
}

func handleGetUnitType(ctx context.Context, clients *Clients, args map[string]any) (*mcp.CallToolResult, error) {
	id, errRes := optionalString(args, "id")
	if errRes != nil {
		return errRes, nil
	}
	code, errRes := optionalString(args, "code")
	if errRes != nil {
		return errRes, nil
	}
	callCtx, cancel := registryCtx(ctx, clients, false)
	defer cancel()
	if id == "" && code == "" {
		listed, err := clients.Units.ListUnitTypes(callCtx, &unitregistrypb.ListUnitTypesRequest{})
		if err != nil {
			return registryError("get_unit_type", err), nil
		}
		views := make([]unitTypeView, 0, len(listed.GetTypes()))
		for _, t := range listed.GetTypes() {
			views = append(views, toUnitTypeView(t))
		}
		sort.Slice(views, func(i, j int) bool { return views[i].Code < views[j].Code })
		return jsonResult(views), nil
	}
	if id != "" && code != "" {
		return errorResult("give either 'id' or 'code', not both"), nil
	}
	found, err := clients.Units.GetUnitType(callCtx, &unitregistrypb.GetUnitTypeRequest{Id: id, Code: code})
	if err != nil {
		return registryError("get_unit_type", err), nil
	}
	return jsonResult(toUnitTypeView(found)), nil
}

func handleSetDimensionTypes(ctx context.Context, clients *Clients, args map[string]any) (*mcp.CallToolResult, error) {
	dimension, errRes := requiredString(args, "dimension")
	if errRes != nil {
		return errRes, nil
	}
	codes, present, errRes := stringList(args, "type_codes")
	if errRes != nil {
		return errRes, nil
	}
	if !present {
		return errorResult("'type_codes' parameter is required ([] clears the dimension's types)"), nil
	}
	callCtx, cancel := registryCtx(ctx, clients, true)
	defer cancel()
	result, err := clients.Units.SetDimensionTypes(callCtx, &unitregistrypb.SetDimensionTypesRequest{
		Dimension: dimension, TypeCodes: codes, UpdatedBy: clients.Actor,
	})
	if err != nil {
		return registryError("set_dimension_types", err), nil
	}
	return jsonResult(map[string]any{"dimension": result.GetDimension(), "type_codes": orEmpty(result.GetTypeCodes())}), nil
}
```

In `internal/tools/registry.go` → `NewRegistry`, after the 4 unit registrations, add:

```go
	r.register("create_unit_type", createUnitTypeDescription, createUnitTypeInputSchema, handleCreateUnitType)
	r.register("update_unit_type", updateUnitTypeDescription, updateUnitTypeInputSchema, handleUpdateUnitType)
	r.register("deactivate_unit_type", deactivateUnitTypeDescription, unitTypeRefInputSchema, handleDeactivateUnitType)
	r.register("get_unit_type", getUnitTypeDescription, unitTypeRefInputSchema, handleGetUnitType)
	r.register("set_dimension_types", setDimensionTypesDescription, setDimensionTypesInputSchema, handleSetDimensionTypes)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `scripts/mcp-normalize-test.sh`
Expected: `ok  github.com/hellopro/mcp-normalize-unite/internal/tools`.
Run: `docker build -f apps-microservices/mcp-normalize-unite-service/Dockerfile -t mcp-normalize-unite:dev .`
Expected: the build succeeds (the Dockerfile now generates both stub packages).

- [ ] **Step 5: Update the MCP `CLAUDE.md`**

In `apps-microservices/mcp-normalize-unite-service/CLAUDE.md`:
- **Backend communication:** add `protos/grpc_stubs/unit_registry.proto` (unit-registry-service).
- Add a **Tools** subsection listing the 11 tools: `normalize_quantity`, `normalize_range`, `create_unit`, `update_unit`, `deactivate_unit`, `get_unit`, `create_unit_type`, `update_unit_type`, `deactivate_unit_type`, `get_unit_type`, `set_dimension_types`. Note that writes send `authorization: Bearer $UNITS_ADMIN_KEY`, and token/code lookups are unauthenticated reads.
- **Env:** add `UNIT_REGISTRY_GRPC_ADDR` (default `unit-registry-service:50059`) and `UNITS_ADMIN_KEY`.
- **Tests:** replace the protogen-stage command with `scripts/mcp-normalize-test.sh`.
- **Folder structure:** add `internal/tools/units.go` and `internal/tools/unit_types.go`.

- [ ] **Step 6: Commit**

```bash
git add apps-microservices/mcp-normalize-unite-service
git commit -m "feat(mcp-normalize-unite-service): unit-type tools (C9)" -m "EN: create/update/deactivate/get_unit_type and set_dimension_types on unit-registry-service. get_unit_type without arguments lists active types so agents reuse codes instead of creating near-duplicates; an empty type_codes list clears a dimension." -m "FR : create/update/deactivate/get_unit_type et set_dimension_types sur unit-registry-service. get_unit_type sans argument liste les types actifs pour que l'agent reutilise un code au lieu d'en creer un quasi-doublon ; une liste type_codes vide vide une dimension."
```

---

### Task 16: Final verification

**Files:** none modified, unless a check fails.

- [ ] **Step 1: Run every suite**

```bash
scripts/unit-registry-test.sh libs/unit-registry -q
scripts/unit-registry-test.sh apps-microservices/unit-registry-service -q
docker exec -w /repo/apps-microservices/unit-registry-service \
  -e MYSQL_TEST_URL='mysql+pymysql://root:test@unit-registry-mysql:3306/normalization_db?charset=utf8mb4' \
  unit-registry-test python -m pytest -q tests/test_mysql.py
scripts/unit-registry-test.sh apps-microservices/graph-rag-normalize-unite-service -q
scripts/mcp-normalize-test.sh
```

Expected: every suite passes. The MySQL suite reports `2 passed` (start `unit-registry-mysql` again with Task 6 Step 6 if it was removed).

- [ ] **Step 2: Build every touched image**

```bash
docker build -f apps-microservices/unit-registry-service/Dockerfile -t unit-registry-service:dev .
docker build -f apps-microservices/graph-rag-normalize-unite-service/Dockerfile -t normalize-unite:dev .
docker build -f apps-microservices/mcp-normalize-unite-service/Dockerfile -t mcp-normalize-unite:dev .
RABBITMQ_URL=amqp://x docker compose --profile graph-rag --profile mcp config --quiet && echo compose-ok
```

Expected: 3 successful builds and `compose-ok`.

- [ ] **Step 3: Check the repo state and clean up**

Run: `git status --short` → expected empty (no stray `go.sum`, `proto/gen`, `extract_legacy_tables.py` or stubs).
Run: `git log --oneline origin/features/poc..HEAD` → expected: the 2 spec commits, the plan commit and 15 task commits.
Clean up: `docker rm -f unit-registry-mysql && docker network rm unit-registry-test-net`.

- [ ] **Step 4: Report**

Summarize to the user:
- the measured test counts per suite;
- the spec deltas P1–P11;
- the two manual deployment steps (run `init-db/10_normalization_db.sh` once on the existing `mysql` volume, and set `UNITS_ADMIN_KEY` and `NORMALIZATION_MYSQL_PASS` in `.env`);
- that the 5 normalizer replicas only switch from fallback to DB tables once `unit-registry-service` is reachable.

Do not open the PR unless asked. The target branch is `features/poc`.
