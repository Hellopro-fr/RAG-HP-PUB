# /dependency-mapper — Cross-Service Dependency Map

Map all inter-service dependencies across the monorepo: imports, gRPC calls, RabbitMQ exchanges, HTTP calls, and shared library usage.

## Process

### Step 1 — Map shared library consumers

For each module in `libs/common-utils/src/common_utils/`:
- Grep all services that import from it.
- Count imports per service.

For `libs/grpc-stubs/`:
- Grep for `from grpc_stubs import` across all services.

For `libs/rust-common-utils/`:
- Check Cargo.toml dependencies in Rust services.

### Step 2 — Map gRPC dependencies

For each proto in `protos/grpc_stubs/`:
- Find all services that import the corresponding `_pb2` or `_pb2_grpc` module.
- Map: producer service → proto → consumer services.

### Step 3 — Map RabbitMQ message flow

Search for:
- `exchange` declarations (publishers)
- `queue` bindings (consumers)
- `routing_key` patterns
- `DLQ` configurations

Map: publisher → exchange → routing_key → queue → consumer.

### Step 4 — Map HTTP inter-service calls

Search for:
- `httpx`, `requests`, `aiohttp` calls with service URLs
- Environment variables pointing to other services (e.g., `API_GATEWAY_URL`)

### Step 5 — Identify critical paths

Find services that are:
- **Most depended upon** (many consumers) — high blast radius
- **Single points of failure** (no redundancy)
- **Chain dependencies** (A → B → C → D)

### Step 6 — Report

```
## Dependency Map

### Shared Library Usage
| Module | Consumer Count | Services |
|--------|---------------|----------|

### gRPC Dependencies
| Proto | Producer | Consumers |
|-------|----------|-----------|

### RabbitMQ Message Flow
| Exchange | Publisher | Routing Key | Consumer |
|----------|----------|-------------|----------|

### HTTP Inter-Service Calls
| Caller | Target Service | Endpoint |
|--------|---------------|----------|

### Critical Path Analysis
| Service | Dependents | Blast Radius | Risk |
|---------|-----------|--------------|------|

### Dependency Graph (text)
[ASCII or mermaid diagram of the most critical dependency chains]
```

## Rules

- Do NOT modify any files. This is a read-only analysis.
- Be exhaustive — check every service.
- Use sub-agents for parallel scanning when checking 90+ services.
- This directly supports `.claude/rules/impact-awareness.md` blast radius checks.
- End with: **"Would you like me to investigate any specific dependency chain?"**
