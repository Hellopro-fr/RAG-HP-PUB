#!/bin/bash
# Creates normalization_db and its user. NOT mounted into the `mysql` compose service (a single-file
# bind inside the read-only docker-entrypoint-initdb.d mount stops mysql from starting). Run it once by
# hand, on fresh and existing volumes alike (command in CLAUDE.md). Tables are created by the service
# itself (plan delta P7).
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
