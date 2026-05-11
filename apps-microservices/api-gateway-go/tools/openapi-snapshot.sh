#!/usr/bin/env bash
# Snapshot the Python api-gateway's /openapi.json (gateway-owned paths only)
# and emit it as YAML for use as base.yaml. Re-run before cutover.
set -euo pipefail
SRC="${SRC:-http://localhost:8500/openapi.json}"
OUT="${OUT:-internal/openapi/base.yaml}"
TMP="$(mktemp)"
curl -fsSL "$SRC" > "$TMP"
python3 - "$TMP" > "$OUT" <<'PY'
import json, sys, yaml
spec = json.load(open(sys.argv[1]))
gateway_paths = {
    "/auth/token/generate","/auth/token/refresh","/auth/token/revoke",
    "/auth/token/refresh-tokens","/auth/token/all-refresh-tokens",
    "/auth/logs","/login","/logout",
    "/auth/login","/auth/callback","/auth/logout-webhook",
    "/openapi.json","/openapi-public.json","/docs","/redoc",
}
spec["paths"] = {p: v for p, v in spec.get("paths", {}).items() if p in gateway_paths}
print(yaml.safe_dump(spec, sort_keys=False, allow_unicode=True))
PY
