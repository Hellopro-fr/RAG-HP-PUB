#!/usr/bin/env bash
# Run the server's integration tests against the compose Postgres (started if needed).
# Every argument is passed to `cargo test -p atb-server`, e.g.:
#   bash scripts/test-pg.sh --test ac_1_1_concurrent_claim
# sqlx::test creates (and drops) one throwaway database per test, as the atb_owner role.
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
  echo ".env is missing: cp .env.example .env and set the passwords" >&2
  exit 1
fi
set -a
# shellcheck disable=SC1091
. ./.env
set +a

docker compose up -d --wait postgres >/dev/null
export DATABASE_URL="postgres://atb_owner:${ATB_OWNER_PASSWORD}@127.0.0.1:${ATB_PG_PORT:-5440}/atb"

# Keep the dev database schema current (it backs the compile-time checked queries).
SQLX_OFFLINE=true cargo run -q -p atb-server -- migrate >/dev/null

exec cargo test -p atb-server "$@"
