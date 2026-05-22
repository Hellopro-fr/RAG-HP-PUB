#!/usr/bin/env bash
# Leak-detection: open N operations against the lib, then assert that within
# GRACE_SECONDS no connections named "{SERVICE_NAME}-*" remain in Redis.
#
# Usage:
#   REDIS_URL=redis://localhost:16379/0 SERVICE_NAME=leak-test \
#       bash libs/common-utils/tests/leak_detect.sh
#
# Env vars (with defaults):
#   REDIS_URL       redis://localhost:16379/0
#   SERVICE_NAME    leak-test
#   N_OPS           100
#   GRACE_SECONDS   30
#
# Exit codes:
#   0  no leak
#   1  connections still present after grace window
#   2  missing dep (python3, redis-cli)

set -euo pipefail

REDIS_URL="${REDIS_URL:-redis://localhost:16379/0}"
SERVICE_NAME="${SERVICE_NAME:-leak-test}"
N_OPS="${N_OPS:-100}"
GRACE_SECONDS="${GRACE_SECONDS:-30}"

command -v python3 >/dev/null 2>&1 || { echo "python3 missing"; exit 2; }
command -v redis-cli >/dev/null 2>&1 || { echo "redis-cli missing"; exit 2; }

# Parse REDIS_URL into redis-cli flags
REDIS_CLI_ARGS=$(python3 -c "
import os, urllib.parse as u
p = u.urlparse(os.environ['REDIS_URL'])
args = ['-h', p.hostname or 'localhost', '-p', str(p.port or 6379)]
if p.password: args += ['-a', p.password]
print(' '.join(args))
")

count_named_conns() {
    redis-cli ${REDIS_CLI_ARGS} CLIENT LIST 2>/dev/null \
        | grep -c "name=${SERVICE_NAME}-" || true
}

baseline=$(count_named_conns)
echo "Baseline conns named '${SERVICE_NAME}-*': ${baseline}"

# Run N short-lived ops via the lib, then close cleanly
export SERVICE_NAME REDIS_URL
python3 -c "
import asyncio, os
from common_utils.redis.cache_service import (
    init_redis_pool, close_redis_pool, set_key, get_key, delete_key,
)

N = int(os.environ.get('N_OPS', '${N_OPS}'))

async def main():
    await init_redis_pool()
    for i in range(N):
        await set_key(f'leaktest:{i}', str(i))
        await get_key(f'leaktest:{i}')
        await delete_key(f'leaktest:{i}')
    await close_redis_pool()
    print(f'Completed {N} ops; closed pool.')

asyncio.run(main())
"

echo "Waiting ${GRACE_SECONDS}s for Redis to register disconnects..."
sleep "${GRACE_SECONDS}"

after=$(count_named_conns)
echo "Post-grace conns named '${SERVICE_NAME}-*': ${after}"

if [ "${after}" -gt "${baseline}" ]; then
    echo "FAIL: $((after - baseline)) conn(s) leaked"
    exit 1
fi
echo "PASS: no leak"
exit 0
