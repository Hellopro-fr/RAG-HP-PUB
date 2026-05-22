# Redis Connection Leak Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop Redis "max clients reached" / ECONNREFUSED loops by capping the Python pool, sharing one Redis client per Node crawl, naming clients for attribution, and enabling server-side idle reap.

**Architecture:** Three client-side prongs (bounded Python pool with keepalive + health check + name, shared Node Redis client factory injected into DedupManager, both reused from a single shared instance in `main.ts`) plus one operator-side `redis-cli` script that applies `CONFIG SET timeout 300` + `tcp-keepalive 60`. Adds one `/admin/redis-debug` FastAPI endpoint + one `redis_diagnose.sh` shell tool for verification.

**Tech Stack:** Python 3.12 (`redis.asyncio`), Node.js 22 (`redis` package), FastAPI, Bash + `redis-cli`, pytest + monkeypatch, `node --import tsx --test`.

---

## Out of scope (deferred follow-ups)

- `StatsManager` (`apps-microservices/crawler-service/crawler/src/class/StatsManager.ts`) opens its own Redis client at `main.ts:547`. Same architectural problem as DedupManager. Deferred — separate spec if observation after rollout shows it still contributes meaningfully to leak.
- Prometheus pool gauges. Spec § 11.3 deferred list.
- `BlockingConnectionPool` / circuit breaker (Approach C in spec).
- Redis topology / HA / sentinel.

## Plan-level test commands

| Layer | Command (run from repo root unless noted) |
|---|---|
| Python (cache_service) | `cd libs/common-utils && pytest tests/test_cache_service.py -v` |
| Python (admin endpoint) | `cd apps-microservices/crawler-service && python -m pytest tests/test_admin_redis_debug.py -v` |
| Node (typecheck) | `cd apps-microservices/crawler-service/crawler && npm run build` |
| Node (unit) | `cd apps-microservices/crawler-service/crawler && npm test` |

---

## Task 1: Bound Python Redis pool — `cache_service.py` + unit tests

**Goal:** Replace `init_redis_pool` body with a bounded, keepalive-protected client + add `_ping_safe` helper. Cover with 6 unit tests.

**Files:**
- Modify: `libs/common-utils/src/common_utils/redis/cache_service.py:18-47`
- Create: `libs/common-utils/tests/test_cache_service.py`

**Acceptance Criteria:**
- [ ] `init_redis_pool` calls `redis.from_url` with `max_connections`, `socket_keepalive=True`, `socket_connect_timeout`, `socket_timeout`, `health_check_interval`, `client_name` kwargs.
- [ ] Env vars override defaults: `REDIS_MAX_CONNECTIONS`, `REDIS_SOCKET_TIMEOUT_S`, `REDIS_SOCKET_CONNECT_TIMEOUT_S`, `REDIS_HEALTH_CHECK_INTERVAL_S`.
- [ ] `REDIS_MAX_CONNECTIONS=0` is clamped to 1.
- [ ] `_ping_safe` swallows exceptions and returns False.
- [ ] Existing-client guard re-uses live client; rebuilds on dead client.
- [ ] All 6 unit tests pass.

**Verify:** `cd libs/common-utils && pytest tests/test_cache_service.py -v` → 6 passed.

**Steps:**

- [ ] **Step 1: Create test file with 6 failing tests**

Path: `libs/common-utils/tests/test_cache_service.py`

```python
"""Tests for common_utils.redis.cache_service.init_redis_pool config."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch):
    """Reset Redis env vars to known defaults so tests are hermetic."""
    for var in (
        "REDIS_URL",
        "REDIS_MAX_CONNECTIONS",
        "REDIS_SOCKET_TIMEOUT_S",
        "REDIS_SOCKET_CONNECT_TIMEOUT_S",
        "REDIS_HEALTH_CHECK_INTERVAL_S",
        "HOSTNAME",
    ):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("REDIS_URL", "redis://:secret@10.0.0.1:6379")
    monkeypatch.setenv("HOSTNAME", "crawler-service-test")


@pytest.fixture
def reset_cache_service():
    """Reset the module-level global so each test starts clean."""
    from common_utils.redis import cache_service
    cache_service.redis_client = None
    yield cache_service
    cache_service.redis_client = None


@pytest.mark.asyncio
async def test_init_uses_bounded_pool_defaults(reset_cache_service):
    mock_client = AsyncMock()
    mock_client.ping = AsyncMock(return_value=True)
    mock_client.register_script = MagicMock(return_value=MagicMock())

    with patch("redis.asyncio.from_url", return_value=mock_client) as from_url:
        await reset_cache_service.init_redis_pool()

    assert from_url.call_count == 1
    _, kwargs = from_url.call_args
    assert kwargs["max_connections"] == 20
    assert kwargs["socket_keepalive"] is True
    assert kwargs["socket_connect_timeout"] == 5
    assert kwargs["socket_timeout"] == 10
    assert kwargs["health_check_interval"] == 30
    assert kwargs["client_name"] == "crawler-py-crawler-service-test"


@pytest.mark.asyncio
async def test_init_reads_env_overrides(reset_cache_service, monkeypatch):
    monkeypatch.setenv("REDIS_MAX_CONNECTIONS", "5")
    monkeypatch.setenv("REDIS_SOCKET_TIMEOUT_S", "7")
    monkeypatch.setenv("REDIS_SOCKET_CONNECT_TIMEOUT_S", "3")
    monkeypatch.setenv("REDIS_HEALTH_CHECK_INTERVAL_S", "15")
    mock_client = AsyncMock()
    mock_client.ping = AsyncMock(return_value=True)
    mock_client.register_script = MagicMock(return_value=MagicMock())

    with patch("redis.asyncio.from_url", return_value=mock_client) as from_url:
        await reset_cache_service.init_redis_pool()

    _, kwargs = from_url.call_args
    assert kwargs["max_connections"] == 5
    assert kwargs["socket_timeout"] == 7
    assert kwargs["socket_connect_timeout"] == 3
    assert kwargs["health_check_interval"] == 15


@pytest.mark.asyncio
async def test_init_clamps_zero_to_one(reset_cache_service, monkeypatch):
    monkeypatch.setenv("REDIS_MAX_CONNECTIONS", "0")
    mock_client = AsyncMock()
    mock_client.ping = AsyncMock(return_value=True)
    mock_client.register_script = MagicMock(return_value=MagicMock())

    with patch("redis.asyncio.from_url", return_value=mock_client) as from_url:
        await reset_cache_service.init_redis_pool()

    _, kwargs = from_url.call_args
    assert kwargs["max_connections"] == 1


@pytest.mark.asyncio
async def test_ping_safe_returns_false_on_exception(reset_cache_service):
    bad_client = AsyncMock()
    bad_client.ping = AsyncMock(side_effect=RuntimeError("boom"))
    result = await reset_cache_service._ping_safe(bad_client)
    assert result is False


@pytest.mark.asyncio
async def test_init_skips_when_existing_client_pings_ok(reset_cache_service):
    live = AsyncMock()
    live.ping = AsyncMock(return_value=True)
    reset_cache_service.redis_client = live

    with patch("redis.asyncio.from_url") as from_url:
        await reset_cache_service.init_redis_pool()

    from_url.assert_not_called()
    assert reset_cache_service.redis_client is live


@pytest.mark.asyncio
async def test_init_rebuilds_when_existing_client_ping_fails(reset_cache_service):
    dead = AsyncMock()
    dead.ping = AsyncMock(side_effect=RuntimeError("conn refused"))
    reset_cache_service.redis_client = dead

    new_client = AsyncMock()
    new_client.ping = AsyncMock(return_value=True)
    new_client.register_script = MagicMock(return_value=MagicMock())

    with patch("redis.asyncio.from_url", return_value=new_client) as from_url:
        await reset_cache_service.init_redis_pool()

    assert from_url.call_count == 1
    assert reset_cache_service.redis_client is new_client
```

- [ ] **Step 2: Run tests, confirm failure**

```bash
cd libs/common-utils && pytest tests/test_cache_service.py -v
```
Expected: 6 failed (function `_ping_safe` not defined, kwargs absent).

- [ ] **Step 3: Replace `init_redis_pool` body + add `_ping_safe`**

Edit `libs/common-utils/src/common_utils/redis/cache_service.py`. Replace lines 18-47 (from `redis_client: redis.Redis | None = None` through end of `init_redis_pool`) with:

```python
# Global Redis client instance
redis_client: redis.Redis | None = None

DEFAULT_MAX_CONNECTIONS = 20
DEFAULT_SOCKET_TIMEOUT_S = 10
DEFAULT_SOCKET_CONNECT_TIMEOUT_S = 5
DEFAULT_HEALTH_CHECK_INTERVAL_S = 30


def _replica_name() -> str:
    # Container hostname is per-replica (docker compose --scale gives unique names).
    return os.getenv("HOSTNAME") or f"pid-{os.getpid()}"


async def _ping_safe(client) -> bool:
    try:
        return await client.ping()
    except Exception:
        return False


async def init_redis_pool():
    """
    Initializes the Redis connection pool with a bounded client + proactive
    health check. See spec docs/superpowers/specs/2026-05-21-redis-connection-leak-fix-design.md.
    """
    global redis_client
    if redis_client and await _ping_safe(redis_client):
        logger.info("Redis pool already initialized and connected.")
        return

    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        logger.critical("REDIS_URL environment variable not set. Caching and state management will be unavailable.")
        redis_client = None
        return

    max_conn = max(1, int(os.getenv("REDIS_MAX_CONNECTIONS", DEFAULT_MAX_CONNECTIONS)))
    sock_to = float(os.getenv("REDIS_SOCKET_TIMEOUT_S", DEFAULT_SOCKET_TIMEOUT_S))
    sock_conn_to = float(os.getenv("REDIS_SOCKET_CONNECT_TIMEOUT_S", DEFAULT_SOCKET_CONNECT_TIMEOUT_S))
    health_iv = int(os.getenv("REDIS_HEALTH_CHECK_INTERVAL_S", DEFAULT_HEALTH_CHECK_INTERVAL_S))
    client_name = f"crawler-py-{_replica_name()}"

    try:
        logging.info(
            f"Connecting to Redis at {redis_url.split('@')[-1]} "
            f"(max_conn={max_conn}, name={client_name})"
        )
        redis_client = redis.from_url(
            redis_url,
            encoding="utf-8",
            decode_responses=True,
            max_connections=max_conn,
            socket_keepalive=True,
            socket_connect_timeout=sock_conn_to,
            socket_timeout=sock_to,
            health_check_interval=health_iv,
            client_name=client_name,
        )
        await redis_client.ping()
        # Register Lua scripts for EVALSHA-based execution.
        global _safe_decr_script, _delete_if_terminal_script
        _safe_decr_script = redis_client.register_script(_SAFE_DECR_LUA)
        _delete_if_terminal_script = redis_client.register_script(_DELETE_IF_TERMINAL_LUA)
        logger.info("Successfully connected to Redis.")
    except redis.RedisError as e:
        logger.warning(f"Could not connect to Redis: {e}. Caching will be unavailable.")
        redis_client = None
```

- [ ] **Step 4: Run tests, confirm pass**

```bash
cd libs/common-utils && pytest tests/test_cache_service.py -v
```
Expected: 6 passed.

- [ ] **Step 5: Run wider unit suite for regression**

```bash
cd libs/common-utils && pytest tests/ -v --ignore=tests/sso
```
Expected: no new failures vs. baseline. Note: skip `tests/sso` (env-dependent).

- [ ] **Step 6: Commit**

Ask user for commit language first (per project rule). Then write `.git/COMMIT_EDITMSG` via the Write tool (UTF-8) — never via shell heredoc:

```
feat(common-utils): bound Redis pool + keepalive + named client

EN:
init_redis_pool now passes max_connections, socket_keepalive,
socket_connect_timeout, socket_timeout, health_check_interval,
client_name to redis.from_url. Defaults 20/5/10/30s; env-overridable.
Adds _ping_safe so the existing-client guard cannot raise. Spec-C 2026-05-21.

FR:
init_redis_pool transmet desormais max_connections, socket_keepalive,
socket_connect_timeout, socket_timeout, health_check_interval,
client_name a redis.from_url. Defauts 20/5/10/30s ; overridable env.
Ajoute _ping_safe pour proteger le garde de client existant. Spec-C 2026-05-21.
```

```bash
git add libs/common-utils/src/common_utils/redis/cache_service.py libs/common-utils/tests/test_cache_service.py
git -c commit.encoding=utf-8 commit -F .git/COMMIT_EDITMSG
```

---

## Task 2: Node shared client factory — `redisClient.ts` + unit tests

**Goal:** Create a side-effect-free factory that returns a single named Redis client. Cover with 4 unit tests.

**Files:**
- Create: `apps-microservices/crawler-service/crawler/src/redisClient.ts`
- Create: `apps-microservices/crawler-service/crawler/src/tests/redisClient.test.ts`

**Acceptance Criteria:**
- [ ] Exports `createSharedRedisClient(url, {crawlId, monitor}) → RedisClientType`.
- [ ] Client created with `name: crawler-node-{crawlId}` and `socket: { keepAlive: 30000, connectTimeout: 5000 }`.
- [ ] Error handler reports to monitor as `'shared'` client name.
- [ ] Module side-effect-free (mirror Spec-A/B extraction pattern).
- [ ] 4 unit tests pass.

**Verify:** `cd apps-microservices/crawler-service/crawler && npm test -- src/tests/redisClient.test.ts && npm run build`

**Steps:**

- [ ] **Step 1: Create test file with 4 failing tests**

Path: `apps-microservices/crawler-service/crawler/src/tests/redisClient.test.ts`

```typescript
import { test } from 'node:test';
import assert from 'node:assert/strict';

// Hoist a module-level capture so the createClient mock can record calls.
const createClientCalls: any[] = [];
const fakeClient: any = {
    on: (_event: string, _handler: (...args: any[]) => void) => fakeClient,
    _emit: (event: string, err: unknown) => {
        for (const [name, handler] of fakeClient._handlers) {
            if (name === event) (handler as any)(err);
        }
    },
    _handlers: new Map<string, (...args: any[]) => void>(),
};

// Re-wire on() to record handlers for synthetic emit.
fakeClient.on = (event: string, handler: (...args: any[]) => void) => {
    fakeClient._handlers.set(event, handler);
    return fakeClient;
};

// Mock the 'redis' module BEFORE the factory imports it.
import { Module } from 'node:module';
const originalResolve = (Module as any)._resolveFilename;
(Module as any)._resolveFilename = function (request: string, ...rest: any[]) {
    if (request === 'redis') return require.resolve('node:path'); // arbitrary placeholder
    return originalResolve.call(this, request, ...rest);
};
// (Above is illustrative; if the project uses tsx + ESM, prefer a per-test
//  import-mocker. The 4 cases below use direct invocation against a mocked
//  createClient via dependency injection. See implementation in Step 3.)

// Cleaner approach: redisClient.ts must export the factory in a form that
// permits a test-time createClient override. Use a tiny seam.

import { __setCreateClientForTests, createSharedRedisClient } from '../redisClient.js';

function resetMock() {
    createClientCalls.length = 0;
    fakeClient._handlers.clear();
    __setCreateClientForTests((opts: any) => {
        createClientCalls.push(opts);
        return fakeClient;
    });
}

test('factory passes name option', () => {
    resetMock();
    createSharedRedisClient('redis://x:6379', { crawlId: 'abc123' });
    assert.equal(createClientCalls.length, 1);
    assert.equal(createClientCalls[0].name, 'crawler-node-abc123');
});

test('factory passes keepAlive 30000 and connectTimeout 5000', () => {
    resetMock();
    createSharedRedisClient('redis://x:6379', { crawlId: 'abc123' });
    const opts = createClientCalls[0];
    assert.equal(opts.socket.keepAlive, 30_000);
    assert.equal(opts.socket.connectTimeout, 5_000);
});

test('error handler reports to monitor as shared', () => {
    resetMock();
    const seen: Array<[string, unknown]> = [];
    const monitor: any = { onError: (name: string, err: unknown) => seen.push([name, err]) };
    createSharedRedisClient('redis://x:6379', { crawlId: 'abc123', monitor });
    const e = new Error('boom');
    fakeClient._emit('error', e);
    assert.equal(seen.length, 1);
    assert.equal(seen[0][0], 'shared');
    assert.equal(seen[0][1], e);
});

test('factory tolerates monitor undefined', () => {
    resetMock();
    createSharedRedisClient('redis://x:6379', { crawlId: 'abc123' });
    // Emitting error must not throw when no monitor is wired.
    assert.doesNotThrow(() => fakeClient._emit('error', new Error('x')));
});
```

- [ ] **Step 2: Run tests, confirm failure**

```bash
cd apps-microservices/crawler-service/crawler && npm test -- src/tests/redisClient.test.ts
```
Expected: FAIL — module `'../redisClient.js'` not found.

- [ ] **Step 3: Create `redisClient.ts` with test seam**

Path: `apps-microservices/crawler-service/crawler/src/redisClient.ts`

```typescript
// Cgroup memory fix Spec-C 2026-05-21 — single named Redis client.
//
// Why single client: each TCP conn to Redis costs a server-side FD. OOM-killed
// Node processes leave orphan conns until server idle-timeout. Halving the
// per-crawl conn count (2 -> 1) halves the orphan blast radius.
//
// Why named: CLIENT LIST attributes conns to a crawl_id for diagnostics.
// `crawler-node-{crawlId}` is unique per crawl + survives reconnect.
//
// Why module: side-effect-free so tests can import without firing main.ts
// top-level execution (same constraint as browserKill.ts + cgroupMemory.ts).

import { createClient as realCreateClient, RedisClientType } from 'redis';
import type { RedisHealthMonitor } from './class/RedisHealthMonitor.js';

export interface SharedRedisClientOpts {
    crawlId: string;
    monitor?: RedisHealthMonitor;
}

// Test seam — production callers ignore this. Tests override via
// __setCreateClientForTests so we can assert the options passed.
let _createClient: typeof realCreateClient = realCreateClient;

export function __setCreateClientForTests(fn: typeof realCreateClient): void {
    _createClient = fn;
}

export function createSharedRedisClient(
    redisUrl: string,
    { crawlId, monitor }: SharedRedisClientOpts,
): RedisClientType {
    const client = _createClient({
        url: redisUrl,
        name: `crawler-node-${crawlId}`,
        socket: {
            keepAlive: 30_000,
            connectTimeout: 5_000,
        },
    }) as RedisClientType;
    client.on('error', (err) => {
        console.error('Redis Client Error:', err);
        monitor?.onError('shared', err);
    });
    return client;
}
```

- [ ] **Step 4: Run tests, confirm pass**

```bash
cd apps-microservices/crawler-service/crawler && npm test -- src/tests/redisClient.test.ts
```
Expected: 4 passed.

- [ ] **Step 5: Run wider Node suite for regression**

```bash
cd apps-microservices/crawler-service/crawler && npm test && npm run build
```
Expected: full suite green; tsc clean.

- [ ] **Step 6: Commit**

Ask language. Write EDITMSG via Write tool:

```
feat(crawler): add shared Redis client factory module

EN:
New redisClient.ts exports createSharedRedisClient — a single named,
keepalive-protected Redis client. Mirrors browserKill.ts + cgroupMemory.ts
extraction pattern (side-effect-free for test imports). 4 unit tests via
test seam on createClient. Spec-C 2026-05-21 Task 2.

FR:
Nouveau module redisClient.ts qui expose createSharedRedisClient : un
client Redis unique, nomme et protege par keepalive. Mirroir du pattern
d'extraction de browserKill.ts + cgroupMemory.ts (sans effet de bord
a l'import test). 4 tests unitaires via une couture de test sur
createClient. Spec-C 2026-05-21 Tache 2.
```

```bash
git add apps-microservices/crawler-service/crawler/src/redisClient.ts apps-microservices/crawler-service/crawler/src/tests/redisClient.test.ts
git -c commit.encoding=utf-8 commit -F .git/COMMIT_EDITMSG
```

---

## Task 3: DedupManager — inject client + unit tests

**Goal:** Allow `DedupManager` to accept either a `RedisClientType` (shared) or a `string` URL (legacy). Cover with 4 unit tests.

**Files:**
- Modify: `apps-microservices/crawler-service/crawler/src/class/DedupManager.ts:4-45`
- Create: `apps-microservices/crawler-service/crawler/src/tests/DedupManager.shared.test.ts`

**Acceptance Criteria:**
- [ ] Constructor accepts `RedisClientType | string` as first arg.
- [ ] `ownsClient=true` (URL path) preserves existing connect/disconnect behavior.
- [ ] `ownsClient=false` (injected client) makes connect/disconnect no-ops.
- [ ] `addUrl` uses `this.redis.sAdd` regardless of which path.
- [ ] 4 unit tests pass.
- [ ] Existing `DedupManager` callers in main.ts still compile until Task 4.

**Verify:** `cd apps-microservices/crawler-service/crawler && npm test -- src/tests/DedupManager.shared.test.ts && npm run build`

**Steps:**

- [ ] **Step 1: Create test file with 4 failing tests**

Path: `apps-microservices/crawler-service/crawler/src/tests/DedupManager.shared.test.ts`

```typescript
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { DedupManager } from '../class/DedupManager.js';

function makeMockClient() {
    const calls: Record<string, any[]> = {
        connect: [],
        disconnect: [],
        sAdd: [],
        expire: [],
    };
    const handlers = new Map<string, (...args: any[]) => void>();
    let isOpen = true;
    const client: any = {
        isOpen,
        on(event: string, handler: (...args: any[]) => void) {
            handlers.set(event, handler);
            return client;
        },
        async connect() { calls.connect.push([]); return client; },
        async disconnect() { calls.disconnect.push([]); return client; },
        async sAdd(key: string, members: string | string[]) {
            calls.sAdd.push([key, members]);
            return Array.isArray(members) ? members.length : 1;
        },
        async expire(key: string, ttl: number) { calls.expire.push([key, ttl]); return 1; },
        _calls: calls,
    };
    return client;
}

test('accepts injected client; connect is no-op', async () => {
    const client = makeMockClient();
    const dedup = new DedupManager(client as any, 'crawl-x');
    await dedup.connect();
    assert.equal(client._calls.connect.length, 0,
        'shared client must NOT be connect()-ed by DedupManager');
});

test('accepts injected client; disconnect is no-op', async () => {
    const client = makeMockClient();
    const dedup = new DedupManager(client as any, 'crawl-x');
    await dedup.disconnect();
    assert.equal(client._calls.disconnect.length, 0,
        'shared client must NOT be disconnect()-ed by DedupManager');
});

test('addUrl uses injected client with dedup:{crawlId} key', async () => {
    const client = makeMockClient();
    const dedup = new DedupManager(client as any, 'crawl-x');
    const isNew = await dedup.addUrl('https://example.com/a');
    assert.equal(client._calls.sAdd.length >= 1, true);
    assert.equal(client._calls.sAdd[0][0], 'dedup:crawl-x');
    assert.equal(client._calls.sAdd[0][1], 'https://example.com/a');
    assert.equal(isNew, true);
});

test('URL form still owns and creates own client (legacy path)', () => {
    const dedup = new DedupManager('redis://x:6379', 'crawl-y');
    // ownsClient is private; we assert via behavior — connect() will attempt
    // a real connection. We only check the instance was constructed without throw.
    assert.ok(dedup);
});
```

- [ ] **Step 2: Run tests, confirm failure**

```bash
cd apps-microservices/crawler-service/crawler && npm test -- src/tests/DedupManager.shared.test.ts
```
Expected: FAIL — current constructor takes `string`, not `RedisClientType | string`.

- [ ] **Step 3: Modify `DedupManager.ts` constructor + connect/disconnect**

Edit `apps-microservices/crawler-service/crawler/src/class/DedupManager.ts`. Replace lines 4-45 (class header through `disconnect()` end) with:

```typescript
export class DedupManager {
    private redis: RedisClientType;
    private monitor?: RedisHealthMonitor;
    private key: string;
    private ttl: number;
    private ttlSet: boolean = false;
    private blockedKey: string;
    private ownsClient: boolean;

    constructor(
        clientOrUrl: RedisClientType | string,
        crawlId: string,
        ttlSeconds: number = 7 * 24 * 3600,
        monitor?: RedisHealthMonitor,
    ) {
        if (typeof clientOrUrl === 'string') {
            // Backward-compatible URL form — DedupManager creates + owns the client.
            this.redis = createClient({ url: clientOrUrl });
            this.ownsClient = true;
            this.redis.on('error', (err) => {
                console.error('Redis Dedup Error:', err);
                this.monitor?.onError('dedup', err);
            });
        } else {
            // Injected shared client — DedupManager does NOT connect/disconnect.
            this.redis = clientOrUrl;
            this.ownsClient = false;
        }
        this.monitor = monitor;
        this.key = `dedup:${crawlId}`;
        this.blockedKey = `blocked_log:${crawlId}`;
        this.ttl = ttlSeconds;
    }

    async connect() {
        if (!this.ownsClient) return;   // shared client connected by owner
        try {
            await this.redis.connect();
            this.monitor?.onSuccess('dedup');
        } catch (e) {
            this.monitor?.onError('dedup', e);
            throw e;
        }
    }

    async disconnect() {
        if (!this.ownsClient) return;   // shared client closed by owner
        if (this.redis.isOpen) {
            try {
                await this.redis.disconnect();
                this.monitor?.onSuccess('dedup');
            } catch (e) {
                this.monitor?.onError('dedup', e);
                throw e;
            }
        }
    }
```

Leave everything below `disconnect()` unchanged. `addUrl`, `isKnown`, `isKnownBatch`, `filterNewBlockedBatch`, `getCount`, `getAllUrlsIterator`, `loadFromIterator`, `cleanup` all call `this.redis.xxx` — works identically whether shared or owned.

- [ ] **Step 4: Run tests, confirm pass**

```bash
cd apps-microservices/crawler-service/crawler && npm test -- src/tests/DedupManager.shared.test.ts && npm run build
```
Expected: 4 passed; build clean.

- [ ] **Step 5: Run wider Node suite for regression**

```bash
cd apps-microservices/crawler-service/crawler && npm test
```
Expected: full suite green (no regression on existing tests).

- [ ] **Step 6: Commit**

Ask language. Write EDITMSG via Write tool:

```
refactor(crawler): DedupManager accepts injected Redis client

EN:
Constructor now takes RedisClientType | string. ownsClient flag preserves
URL-form backward compat (legacy callers + tests). Injected-client path
makes connect/disconnect no-ops so the owner manages the connection
lifecycle. 4 unit tests. Spec-C 2026-05-21 Task 3.

FR:
Le constructeur accepte desormais RedisClientType | string. Le drapeau
ownsClient preserve la retrocompat de la forme URL (anciens appelants +
tests). Le chemin client-injecte rend connect/disconnect no-op, la gestion
de la connexion est deleguee au proprietaire. 4 tests unitaires.
Spec-C 2026-05-21 Tache 3.
```

```bash
git add apps-microservices/crawler-service/crawler/src/class/DedupManager.ts apps-microservices/crawler-service/crawler/src/tests/DedupManager.shared.test.ts
git -c commit.encoding=utf-8 commit -F .git/COMMIT_EDITMSG
```

---

## Task 4: Wire shared client in `main.ts`

**Goal:** Replace the two separate `createClient` calls (heartbeat at L361, DedupManager URL at L546) with a single shared client created up front and reused by both.

**Files:**
- Modify: `apps-microservices/crawler-service/crawler/src/main.ts:5,29,361-488,546-581`

**Acceptance Criteria:**
- [ ] Only one `createClient` call remains in `main.ts` (via `createSharedRedisClient`).
- [ ] Heartbeat publish uses the shared client; success/error reported to monitor as `'shared'`.
- [ ] DedupManager constructed with shared client; `dedup.connect()` is a no-op.
- [ ] DropData reconnect path (lines ~570-581) no longer needs to reconnect (shared client unaffected by `dedup.cleanup()`).
- [ ] `gracefulShutdown` closes shared client once.
- [ ] Existing fail-fast `process.exit(5)` on shared connect failure preserved.
- [ ] Build clean; existing tests pass.

**Verify:** `cd apps-microservices/crawler-service/crawler && grep -c "createClient(" src/main.ts ; npm test && npm run build`

**Steps:**

- [ ] **Step 1: Add import at top of main.ts**

Edit `apps-microservices/crawler-service/crawler/src/main.ts`. Locate the existing redis import on line 5 (`import { createClient } from 'redis';`). Remove it (we no longer need raw `createClient`). Add right after the existing import block (after line 44):

```typescript
import { createSharedRedisClient } from "./redisClient.js";
```

- [ ] **Step 2: Replace heartbeat block (lines 360-488)**

Replace from line 360 (`// --- Heartbeat Mechanism ---`) through line 488 (`// ---------------------------`) with:

```typescript
// --- Shared Redis client (heartbeat + dedup multiplex) ---
const sharedRedis = createSharedRedisClient(redisUrl, { crawlId: id, monitor: redisMonitor });
try {
    await sharedRedis.connect();
    redisMonitor.onSuccess('shared');
    console.log('Connected to Redis (shared client for heartbeat + dedup)');

    const hostname = os.hostname();
    const numCpus = os.cpus().length;
    let lastCpuUsage = process.cpuUsage();
    let lastTime = Date.now();

    // Helper to get top 3 RAM processes
    const getTopProcesses = async (): Promise<Array<{ name: string, ram: number }>> => {
        try {
            const { execSync } = await import('child_process');
            const output = execSync('ps aux --sort=-rss | head -n 4 | tail -n 3', { encoding: 'utf-8' });
            const lines = output.trim().split('\n');
            return lines.map(line => {
                const parts = line.trim().split(/\s+/);
                const ramKB = parseInt(parts[5]) || 0;
                const command = parts.slice(10).join(' ').substring(0, 30);
                return { name: command, ram: ramKB * 1024 };
            });
        } catch (e) {
            return [];
        }
    };

    // Helper to read container-level memory usage from cgroups
    const getContainerMemoryUsage = async (): Promise<number> => {
        try {
            const v2 = await fsPromises.readFile('/sys/fs/cgroup/memory.current', 'utf-8').catch(() => null);
            if (v2) return parseInt(v2.trim());
            const v1 = await fsPromises.readFile('/sys/fs/cgroup/memory/memory.usage_in_bytes', 'utf-8').catch(() => null);
            if (v1) return parseInt(v1.trim());
        } catch (e) { /* fallback below */ }
        return process.memoryUsage().rss;
    };

    // Helper to read container-level CPU usage from cgroups
    const getContainerCpuUsec = async (): Promise<number | null> => {
        try {
            const v2 = await fsPromises.readFile('/sys/fs/cgroup/cpu.stat', 'utf-8').catch(() => null);
            if (v2) {
                const match = v2.match(/usage_usec\s+(\d+)/);
                if (match) return parseInt(match[1]);
            }
            const v1 = await fsPromises.readFile('/sys/fs/cgroup/cpuacct/cpuacct.usage', 'utf-8').catch(() => null);
            if (v1) return parseInt(v1.trim()) / 1000;
        } catch (e) { /* fallback below */ }
        return null;
    };

    let lastContainerCpuUsec = await getContainerCpuUsec();
    let lastContainerCpuTime = Date.now();

    setInterval(async () => {
        try {
            let cpuPercent: number;
            const currentContainerCpuUsec = await getContainerCpuUsec();
            const currentTime = Date.now();

            if (currentContainerCpuUsec !== null && lastContainerCpuUsec !== null) {
                const deltaCpuUsec = currentContainerCpuUsec - lastContainerCpuUsec;
                const deltaWallUsec = (currentTime - lastContainerCpuTime) * 1000;
                cpuPercent = (deltaCpuUsec / deltaWallUsec) / numCpus;
                lastContainerCpuUsec = currentContainerCpuUsec;
                lastContainerCpuTime = currentTime;
            } else {
                const currentCpuUsage = process.cpuUsage(lastCpuUsage);
                const elapsedTime = (currentTime - lastTime) * 1000;
                cpuPercent = ((currentCpuUsage.user + currentCpuUsage.system) / elapsedTime) / numCpus;
                lastCpuUsage = process.cpuUsage();
                lastTime = currentTime;
            }

            const containerRam = await getContainerMemoryUsage();
            const topProcesses = await getTopProcesses();

            const heartbeat = {
                type: 'heartbeat',
                replicaId: hostname,
                jobId: id,
                domain: domain,
                cpu: Math.min(Math.max(cpuPercent, 0), 1),
                ram: containerRam,
                totalRam: totalMem,
                topProcesses: topProcesses,
                timestamp: Date.now(),
                status: 'running'
            };
            try {
                await sharedRedis.publish('crawler:heartbeat', JSON.stringify(heartbeat));
                redisMonitor.onSuccess('shared');
            } catch (e) {
                redisMonitor.onError('shared', e);
                console.error('Failed to send heartbeat:', e);
            }
        } catch (e) {
            console.error('Heartbeat interval error:', e);
        }
    }, 2000);
} catch (err) {
    console.error('Failed to connect shared Redis client:', err);
    redisMonitor.onError('shared', err);
    redisMonitor.stop();
    process.exit(5);
}
// ---------------------------
```

- [ ] **Step 3: Replace DedupManager construction + connect (lines 546-556)**

Find lines 546-556 (the `new DedupManager(redisUrl, ...)` + `dedup.connect()` block). Replace with:

```typescript
// Init Managers — DedupManager reuses the shared Redis client.
context.dedupManager = new DedupManager(sharedRedis, id, undefined, redisMonitor);
context.statsManager = new StatsManager(redisUrl, id, storagePath || ".");
// No dedupManager.connect() — shared client already connected above.
await context.statsManager.connect();
```

Drop the try/catch around `dedupManager.connect()` — there is no connect call to fail. (Failure to connect the shared client already exits 5 in Step 2's block.)

- [ ] **Step 4: Adjust dropData reconnect path (lines ~570-581)**

Find the dropData block that calls `context.dedupManager.cleanup()` then re-runs `context.dedupManager.connect()`. Replace with:

```typescript
    // Also clean managers
    await context.dedupManager.cleanup();
    await context.statsManager.cleanup();
    // Shared client survives cleanup (dedup.cleanup no longer disconnects it
    // because ownsClient=false). No reconnect needed for dedupManager.
    await context.statsManager.connect();
```

- [ ] **Step 5: Update `gracefulShutdown` to close shared client once**

Locate the existing `gracefulShutdown` function. After existing teardown (stopping monitors, cleaning dedup), add before `process.exit(...)`:

```typescript
    try {
        if (sharedRedis.isOpen) await sharedRedis.disconnect();
    } catch (e) {
        console.error('Shared Redis disconnect error:', e);
    }
```

If `gracefulShutdown` is declared above the `sharedRedis` const (forward reference), the existing pattern of accessing it via closure at fire-time keeps working. Verify by build.

- [ ] **Step 6: Build + sanity grep**

```bash
cd apps-microservices/crawler-service/crawler && grep -nE "createClient\(" src/main.ts
```
Expected: 0 matches (createClient only in `redisClient.ts` + `class/DedupManager.ts` legacy URL branch).

```bash
cd apps-microservices/crawler-service/crawler && npm run build && npm test
```
Expected: tsc clean; all tests green.

- [ ] **Step 7: Commit**

Ask language. Write EDITMSG via Write tool:

```
refactor(crawler): main.ts uses shared Redis client for heartbeat + dedup

EN:
Replaces two separate createClient calls (heartbeat L361, DedupManager
L546) with a single shared client built via createSharedRedisClient.
Heartbeat publishes + DedupManager ops multiplex on the same TCP conn.
Halves per-crawl conn count (2 -> 1). Spec-C 2026-05-21 Task 4.

FR:
Remplace les deux appels createClient distincts (heartbeat L361,
DedupManager L546) par un client partage unique construit via
createSharedRedisClient. Les publish heartbeat + ops DedupManager se
multiplexent sur la meme connexion TCP. Divise par deux le nombre de
connexions par crawl (2 -> 1). Spec-C 2026-05-21 Tache 4.
```

```bash
git add apps-microservices/crawler-service/crawler/src/main.ts
git -c commit.encoding=utf-8 commit -F .git/COMMIT_EDITMSG
```

---

## Task 5: `/admin/redis-debug` endpoint

**Goal:** Add an authenticated endpoint that returns per-replica Redis pool stats + global `CLIENT LIST` aggregation for incident debugging.

**Files:**
- Create: `apps-microservices/crawler-service/app/router/admin.py`
- Modify: `apps-microservices/crawler-service/main.py:11,178` (import + include_router)
- Create: `apps-microservices/crawler-service/tests/test_admin_redis_debug.py`

**Acceptance Criteria:**
- [ ] `GET /admin/redis-debug` returns JSON with `info_clients`, `total_clients`, `client_name_counts`, `client_addr_counts`, `sample_clients` (cap 50), `pool_stats`.
- [ ] Endpoint protected by existing `verify_api_key` dependency.
- [ ] Returns 503 when `redis_client is None`.
- [ ] `pool_stats` errors are caught (return `{"error": "..."}`).
- [ ] Registered in `main.py` after existing routers.
- [ ] 3 unit tests pass.

**Verify:** `cd apps-microservices/crawler-service && python -m pytest tests/test_admin_redis_debug.py -v`

**Steps:**

- [ ] **Step 1: Create test file with 3 failing tests**

Path: `apps-microservices/crawler-service/tests/test_admin_redis_debug.py`

```python
"""Tests for /admin/redis-debug endpoint."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def app_with_admin_router(monkeypatch):
    """Build a minimal FastAPI app with only the admin router mounted."""
    monkeypatch.setenv("API_KEY", "")  # disable auth for these tests
    # Defer import so settings re-read env.
    from app.core.config import settings
    monkeypatch.setattr(settings, "API_KEY", None, raising=False)
    from app.router.admin import router as AdminRouter
    app = FastAPI()
    app.include_router(AdminRouter)
    return app


def test_returns_503_when_redis_client_none(app_with_admin_router, monkeypatch):
    from common_utils.redis import cache_service
    monkeypatch.setattr(cache_service, "redis_client", None, raising=False)
    client = TestClient(app_with_admin_router)
    resp = client.get("/admin/redis-debug")
    assert resp.status_code == 503


def test_returns_full_snapshot_when_redis_alive(app_with_admin_router, monkeypatch):
    fake = AsyncMock()
    fake.info = AsyncMock(return_value={"connected_clients": "42"})
    fake.client_list = AsyncMock(return_value=[
        {"name": "crawler-py-r1", "addr": "10.0.0.1:1"},
        {"name": "crawler-py-r1", "addr": "10.0.0.1:2"},
        {"name": "crawler-node-abc", "addr": "10.0.0.2:1"},
    ])
    pool = MagicMock()
    pool.max_connections = 20
    pool._created_connections = 3
    pool._available_connections = [object(), object()]
    pool._in_use_connections = {object(): None}
    fake.connection_pool = pool

    from common_utils.redis import cache_service
    monkeypatch.setattr(cache_service, "redis_client", fake, raising=False)

    client = TestClient(app_with_admin_router)
    resp = client.get("/admin/redis-debug")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_clients"] == 3
    assert body["info_clients"]["connected_clients"] == "42"
    name_counts = dict(body["client_name_counts"])
    assert name_counts["crawler-py-r1"] == 2
    assert name_counts["crawler-node-abc"] == 1
    assert body["pool_stats"]["max_connections"] == 20
    assert body["pool_stats"]["in_use"] == 1


def test_pool_stats_failure_does_not_500(app_with_admin_router, monkeypatch):
    fake = AsyncMock()
    fake.info = AsyncMock(return_value={"connected_clients": "1"})
    fake.client_list = AsyncMock(return_value=[])
    # No connection_pool attribute → AttributeError in _pool_stats.
    type(fake).connection_pool = property(lambda self: (_ for _ in ()).throw(AttributeError("nope")))

    from common_utils.redis import cache_service
    monkeypatch.setattr(cache_service, "redis_client", fake, raising=False)

    client = TestClient(app_with_admin_router)
    resp = client.get("/admin/redis-debug")
    assert resp.status_code == 200
    assert "error" in resp.json()["pool_stats"]
```

- [ ] **Step 2: Run tests, confirm failure**

```bash
cd apps-microservices/crawler-service && python -m pytest tests/test_admin_redis_debug.py -v
```
Expected: import error — `app.router.admin` not found.

- [ ] **Step 3: Create the admin router**

Path: `apps-microservices/crawler-service/app/router/admin.py`

```python
"""Admin/operator endpoints. Authenticated. Not user-facing."""
import logging
from collections import Counter
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException

from app.core.auth import verify_api_key
from common_utils.redis import cache_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["Admin"])


def _count_by(clients: list, key: str) -> list:
    return Counter(c.get(key, "<unset>") for c in clients).most_common(20)


def _pool_stats(client) -> Dict[str, Any]:
    try:
        pool = client.connection_pool
        return {
            "max_connections": getattr(pool, "max_connections", None),
            "created_connections": getattr(pool, "_created_connections", None),
            "available": len(getattr(pool, "_available_connections", []) or []),
            "in_use": len(getattr(pool, "_in_use_connections", {}) or {}),
        }
    except Exception as e:
        return {"error": str(e)}


@router.get("/redis-debug", dependencies=[Depends(verify_api_key)])
async def redis_debug():
    """
    Operator-only snapshot of this replica's Redis pool + global CLIENT LIST.
    See docs/superpowers/specs/2026-05-21-redis-connection-leak-fix-design.md.
    """
    client = cache_service.redis_client
    if client is None:
        raise HTTPException(status_code=503, detail="Redis not connected")
    try:
        info = await client.info("clients")
        all_clients = await client.client_list()
        return {
            "info_clients": info,
            "total_clients": len(all_clients),
            "client_name_counts": _count_by(all_clients, "name"),
            "client_addr_counts": _count_by(all_clients, "addr"),
            "sample_clients": all_clients[:50],
            "pool_stats": _pool_stats(client),
        }
    except Exception as e:
        logger.error(f"redis-debug failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"redis-debug failed: {e}")
```

- [ ] **Step 4: Register router in `main.py`**

Edit `apps-microservices/crawler-service/main.py`. After the existing import line 11:

```python
from app.router.migration import router as MigrationRouter  # TODO: Remove after migration complete
from app.router.admin import router as AdminRouter
```

After the existing `include_router` calls at line 178-179:

```python
app.include_router(CrawlerRouter, tags=["Crawler"])
app.include_router(MigrationRouter, prefix="/migration", tags=["Migration (Temporary)"])
app.include_router(AdminRouter)
```

- [ ] **Step 5: Run tests, confirm pass**

```bash
cd apps-microservices/crawler-service && python -m pytest tests/test_admin_redis_debug.py -v
```
Expected: 3 passed.

- [ ] **Step 6: Run wider crawler-service Python suite for regression**

```bash
cd apps-microservices/crawler-service && python -m pytest tests/ -x -q --ignore=tests/test_api.py --ignore=tests/test_domain_fr.py
```
Expected: no new failures (skip pre-existing broken local tests documented in primer).

- [ ] **Step 7: Commit**

Ask language. Write EDITMSG via Write tool:

```
feat(crawler-service): add /admin/redis-debug endpoint

EN:
New admin router with /admin/redis-debug returning per-replica pool stats
+ global CLIENT LIST aggregation (name + addr counts, sample 50). Auth via
existing verify_api_key. 3 unit tests. Spec-C 2026-05-21 Task 5.

FR:
Nouveau routeur admin avec /admin/redis-debug qui retourne les stats du
pool par replica + agregation globale CLIENT LIST (compteurs name + addr,
echantillon 50). Auth via le verify_api_key existant. 3 tests unitaires.
Spec-C 2026-05-21 Tache 5.
```

```bash
git add apps-microservices/crawler-service/app/router/admin.py apps-microservices/crawler-service/main.py apps-microservices/crawler-service/tests/test_admin_redis_debug.py
git -c commit.encoding=utf-8 commit -F .git/COMMIT_EDITMSG
```

---

## Task 6: `redis_diagnose.sh` operator script

**Goal:** A single shell script mirroring `scale_crawlers.sh` style that prints Redis config + connection stats and (optionally) applies the server-side idle reap.

**Files:**
- Create: `apps-microservices/crawler-service/redis_diagnose.sh`

**Acceptance Criteria:**
- [ ] Bash + redis-cli + `.env`-driven.
- [ ] Prints: `CONFIG GET maxclients|timeout|tcp-keepalive|maxmemory`, `INFO clients`, top 20 addrs, top 20 client names.
- [ ] `--apply-timeout` flag runs `CONFIG SET timeout 300 + CONFIG SET tcp-keepalive 60 + CONFIG REWRITE`.
- [ ] `chmod +x` applied.
- [ ] `bash -n` lint clean.

**Verify:** `bash -n apps-microservices/crawler-service/redis_diagnose.sh && head -5 apps-microservices/crawler-service/redis_diagnose.sh`

**Steps:**

- [ ] **Step 1: Create the script**

Path: `apps-microservices/crawler-service/redis_diagnose.sh`

```bash
#!/bin/bash
# ==============================================================================
# redis_diagnose.sh — Operator-side Redis connection diagnostic.
#
# Mirrors scale_crawlers.sh: loads .env, runs redis-cli against external Redis.
# Use BEFORE applying server-side CONFIG SET + AFTER fix deploys to verify.
#
# Usage:
#   ./redis_diagnose.sh                  # diagnostic only (no writes)
#   ./redis_diagnose.sh --apply-timeout  # also runs CONFIG SET timeout 300
#                                        # + tcp-keepalive 60 + REWRITE
#
# Spec: docs/superpowers/specs/2026-05-21-redis-connection-leak-fix-design.md
# ==============================================================================

set -e

if ! command -v redis-cli &> /dev/null; then
    echo "ERROR: redis-cli not installed. Install redis-tools (or equivalent)."
    exit 1
fi

if [ ! -f .env ]; then
    echo "ERROR: .env not found. Run from the repo root (where docker compose runs)."
    exit 1
fi

set -o allexport
source .env
set +o allexport

if [ -z "$REDIS_HOST" ] || [ -z "$REDIS_PORT" ] || [ -z "$REDIS_SECRET" ]; then
    echo "ERROR: REDIS_HOST / REDIS_PORT / REDIS_SECRET missing in .env."
    exit 1
fi

RCLI=(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" -a "$REDIS_SECRET" --no-auth-warning)

echo "===================================================="
echo " Redis @ $REDIS_HOST:$REDIS_PORT"
echo "===================================================="

echo ""
echo "=== Server config ==="
"${RCLI[@]}" CONFIG GET maxclients
"${RCLI[@]}" CONFIG GET timeout
"${RCLI[@]}" CONFIG GET tcp-keepalive
"${RCLI[@]}" CONFIG GET maxmemory

echo ""
echo "=== Connection stats ==="
"${RCLI[@]}" INFO clients

echo ""
echo "=== Top 20 clients by addr ==="
"${RCLI[@]}" CLIENT LIST | awk '{print $2, $4}' | sort | uniq -c | sort -rn | head -20

echo ""
echo "=== Client name distribution ==="
"${RCLI[@]}" CLIENT LIST | grep -oP 'name=\K[^ ]+' | sort | uniq -c | sort -rn | head -20

if [ "$1" = "--apply-timeout" ]; then
    echo ""
    echo "=== Applying server-side idle reap ==="
    "${RCLI[@]}" CONFIG SET timeout 300
    "${RCLI[@]}" CONFIG SET tcp-keepalive 60
    "${RCLI[@]}" CONFIG REWRITE
    echo "Done. New conns will be reaped after 300s idle."
fi
```

- [ ] **Step 2: Make executable + lint**

```bash
chmod +x apps-microservices/crawler-service/redis_diagnose.sh
bash -n apps-microservices/crawler-service/redis_diagnose.sh
```
Expected: chmod succeeds; `bash -n` exits 0.

- [ ] **Step 3: Commit**

Ask language. Write EDITMSG via Write tool:

```
feat(crawler-service): add redis_diagnose.sh operator tool

EN:
New shell script mirroring scale_crawlers.sh pattern (loads .env, runs
redis-cli). Prints CONFIG + INFO clients + top 20 client names/addrs.
--apply-timeout applies CONFIG SET timeout 300 + tcp-keepalive 60 +
REWRITE for orphan reap. Spec-C 2026-05-21 Task 6.

FR:
Nouveau script shell qui suit le pattern de scale_crawlers.sh (charge
.env, execute redis-cli). Affiche CONFIG + INFO clients + top 20 noms/
addrs clients. --apply-timeout applique CONFIG SET timeout 300 +
tcp-keepalive 60 + REWRITE pour reaper les orphelins. Spec-C 2026-05-21
Tache 6.
```

```bash
git add apps-microservices/crawler-service/redis_diagnose.sh
git -c commit.encoding=utf-8 commit -F .git/COMMIT_EDITMSG
```

---

## Task 7: `docker-compose.yml` env passthroughs + `CLAUDE.md` docs

**Goal:** Surface the 4 Python env knobs in compose + document the new endpoint, script, and rollout playbook in the crawler-service CLAUDE.md.

**Files:**
- Modify: `docker-compose.yml:1356-1363` (crawler-service `environment` block)
- Modify: `apps-microservices/crawler-service/CLAUDE.md`

**Acceptance Criteria:**
- [ ] `docker-compose.yml` has `REDIS_MAX_CONNECTIONS`, `REDIS_SOCKET_TIMEOUT_S`, `REDIS_SOCKET_CONNECT_TIMEOUT_S`, `REDIS_HEALTH_CHECK_INTERVAL_S` lines on `crawler-service`.
- [ ] `docker compose config` validates clean.
- [ ] CLAUDE.md has a new "Redis Connection Leak Prevention" section + endpoint + script documentation.
- [ ] CLAUDE.md grep for `REDIS_MAX_CONNECTIONS` returns at least one match.

**Verify:** `docker compose -f docker-compose.yml config --quiet && grep -c "REDIS_MAX_CONNECTIONS" apps-microservices/crawler-service/CLAUDE.md`

**Steps:**

- [ ] **Step 1: Add env passthroughs to docker-compose.yml**

Edit `docker-compose.yml`. Locate the `crawler-service:` block (line 1336) and its `environment:` section (line 1356). After the existing `PROGRESS_STALL_THRESHOLD_MS` line (1363), append:

```yaml
      - REDIS_MAX_CONNECTIONS=${REDIS_MAX_CONNECTIONS:-20}
      - REDIS_SOCKET_TIMEOUT_S=${REDIS_SOCKET_TIMEOUT_S:-10}
      - REDIS_SOCKET_CONNECT_TIMEOUT_S=${REDIS_SOCKET_CONNECT_TIMEOUT_S:-5}
      - REDIS_HEALTH_CHECK_INTERVAL_S=${REDIS_HEALTH_CHECK_INTERVAL_S:-30}
```

- [ ] **Step 2: Validate compose**

```bash
docker compose -f docker-compose.yml config --quiet
```
Expected: exit 0 (no output on success).

- [ ] **Step 3: Add CLAUDE.md section**

Edit `apps-microservices/crawler-service/CLAUDE.md`. After the "Redis Loss / Progress Stall Detection" section (before "Capacity Counter Invariants"), insert:

```markdown
## Redis Connection Leak Prevention

Three client-side prongs + one operator-side step prevent the connection-cap exhaustion that recurred until each crawler-service restart.

### Python side (`libs/common-utils` cache_service)

`init_redis_pool()` now builds a bounded, keepalive-protected client with proactive health checks. All connections are named per-replica for `CLIENT LIST` attribution.

| Env var | Default | Purpose |
|---------|---------|---------|
| `REDIS_MAX_CONNECTIONS` | `20` | Pool cap per replica |
| `REDIS_SOCKET_TIMEOUT_S` | `10` | Per-command timeout |
| `REDIS_SOCKET_CONNECT_TIMEOUT_S` | `5` | Connect handshake timeout |
| `REDIS_HEALTH_CHECK_INTERVAL_S` | `30` | Proactive ping cadence |

`max_connections=0` is clamped to 1. When the pool is exhausted, `redis-py` raises `ConnectionError("Too many connections")` — surfaces as a 500 to the API caller, points us at the leak source rather than silently growing.

Client name: `crawler-py-{HOSTNAME or pid-N}`.

### Node side (crawler subprocess)

Heartbeat publishes and `DedupManager` operations now multiplex on a single shared Redis client created via `createSharedRedisClient(redisUrl, { crawlId, monitor })` in `crawler/src/redisClient.ts`. Halves per-crawl conn count (2 → 1) and halves the orphan blast radius when the process is OOM-killed.

`DedupManager` accepts `RedisClientType | string` — the URL form is preserved for backward compat (tests + legacy callers).

Client name: `crawler-node-{crawlId}`.

Note: `StatsManager` still opens its own Redis client. Deferred follow-up — see spec § Deferred follow-ups.

### Server-side idle reap

`./redis_diagnose.sh --apply-timeout` (run once from the deploy host) sets:

- `CONFIG SET timeout 300` — server reaps idle conns after 5 min.
- `CONFIG SET tcp-keepalive 60` — TCP-level keepalive every 60s.
- `CONFIG REWRITE` — persists to `redis.conf` so the setting survives restart.

These complement the client-side keepalive — TCP-half-open conns left behind by SIGKILL'd Node processes are reaped automatically.

### Diagnostic tools

| Tool | View | Use |
|------|------|-----|
| `./redis_diagnose.sh` (root) | Server-side global | All conns Redis sees, names + addrs, config |
| `GET /admin/redis-debug` | Per-replica local | This replica's pool stats + global CLIENT LIST aggregation |

The endpoint is authenticated via existing `verify_api_key` (`X-API-Key` header).

### Rollout (post-deploy)

1. Run `./redis_diagnose.sh` baseline → record `connected_clients`, name distribution.
2. Run `./redis_diagnose.sh --apply-timeout` once.
3. Deploy code (Python pool + Node shared client + admin endpoint together).
4. Run `./redis_diagnose.sh` again → expect `crawler-node-*` count = active crawls (not 2× active crawls); `timeout=300`; orphan count drops within 5 min.
5. Curl `/admin/redis-debug` per replica → expect `pool_stats.in_use` well below `max_connections`.

Spec: `docs/superpowers/specs/2026-05-21-redis-connection-leak-fix-design.md`.
Plan: `docs/superpowers/plans/2026-05-21-redis-connection-leak-fix.md`.
```

- [ ] **Step 4: Verify CLAUDE.md grep**

```bash
grep -c "REDIS_MAX_CONNECTIONS" apps-microservices/crawler-service/CLAUDE.md
```
Expected: ≥ 1.

- [ ] **Step 5: Commit**

Ask language. Write EDITMSG via Write tool:

```
docs(crawler-service): redis conn leak rollout playbook + env knobs

EN:
docker-compose passes through REDIS_MAX_CONNECTIONS / SOCKET_TIMEOUT_S /
SOCKET_CONNECT_TIMEOUT_S / HEALTH_CHECK_INTERVAL_S to the crawler-service
container. CLAUDE.md gains a Redis Connection Leak Prevention section
covering Python pool knobs, Node shared client, server-side reap, and
the 5-step post-deploy rollout. Spec-C 2026-05-21 Task 7.

FR:
docker-compose propage REDIS_MAX_CONNECTIONS / SOCKET_TIMEOUT_S /
SOCKET_CONNECT_TIMEOUT_S / HEALTH_CHECK_INTERVAL_S au conteneur
crawler-service. CLAUDE.md gagne une section Redis Connection Leak
Prevention qui couvre les knobs du pool Python, le client Node partage,
le reap cote serveur et le rollout post-deploy en 5 etapes.
Spec-C 2026-05-21 Tache 7.
```

```bash
git add docker-compose.yml apps-microservices/crawler-service/CLAUDE.md
git -c commit.encoding=utf-8 commit -F .git/COMMIT_EDITMSG
```

---

## Self-review checklist

| Spec requirement | Task |
|---|---|
| Python pool bounded + keepalive + health + named | T1 |
| `_ping_safe` helper | T1 |
| Env knobs + defaults | T1 |
| Node shared client factory | T2 |
| DedupManager accepts injected client | T3 |
| main.ts uses shared client for heartbeat + dedup | T4 |
| gracefulShutdown closes shared client | T4 (Step 5) |
| `/admin/redis-debug` endpoint | T5 |
| Pool stats failure safe | T5 (Step 3 + test) |
| `redis_diagnose.sh` (read-only + `--apply-timeout`) | T6 |
| Compose env passthroughs | T7 |
| CLAUDE.md rollout + tables | T7 |
| Backward compat for DedupManager URL form | T3 + T4 |

No placeholders. All steps have exact code. All file paths absolute or repo-relative. All verify commands have expected output. Type names consistent across tasks (`RedisClientType`, `SharedRedisClientOpts`, `createSharedRedisClient`).
