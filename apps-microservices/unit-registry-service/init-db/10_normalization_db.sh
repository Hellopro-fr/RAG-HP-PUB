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
