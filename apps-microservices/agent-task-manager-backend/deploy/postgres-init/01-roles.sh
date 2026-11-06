#!/bin/sh
# Creates the two application roles. Runs once, on an empty data directory.
#   atb_owner: owns the database, runs migrations (DATABASE_OWNER_URL); CREATEDB for sqlx::test.
#   atb_app:   runtime role (DATABASE_URL); no UPDATE/DELETE on events (see migrations/0008).
set -eu
: "${ATB_OWNER_PASSWORD:?ATB_OWNER_PASSWORD is required}"
: "${ATB_APP_PASSWORD:?ATB_APP_PASSWORD is required}"
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres \
  -v owner_pw="$ATB_OWNER_PASSWORD" -v app_pw="$ATB_APP_PASSWORD" <<'SQL'
CREATE ROLE atb_owner LOGIN CREATEDB PASSWORD :'owner_pw';
CREATE ROLE atb_app LOGIN PASSWORD :'app_pw';
GRANT atb_app TO atb_owner;
CREATE DATABASE atb OWNER atb_owner;
SQL
