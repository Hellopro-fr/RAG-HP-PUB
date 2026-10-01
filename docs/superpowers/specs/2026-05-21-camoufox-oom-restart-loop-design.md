# Camoufox / Browser-Engine Kill-Pattern Widening (OOM Restart Loop Fix)

> **Date:** 2026-05-21
> **Status:** Approved — ready for plan writing
> **Repo:** `RAG-HP-PUB`
> **Branch:** `features/poc`
> **Service:** `apps-microservices/crawler-service`
> **Companion (sequenced):** `docs/superpowers/specs/2026-05-21-cgroup-memory-measurement-correction-design.md` (Spec-B, not yet written — addresses the page-cache false-positive lever).

---

## 1. Problem

Production crawler-service hit an infinite OOM_RELAUNCH loop on `shop.monlabofermier.fr` (crawl id `6334`). Symptoms captured in `crawler.log`:

1. Normal crawl runs ~76 min, hits Tier 2 memory critical (92%+).
2. Tier 2 Phase A recovery runs: `[Phase A] Killing all Chrome/Playwright processes` → memory still 93%+.
3. Phase B fires → graceful shutdown → exit code 3 (`OOM_RELAUNCH`).
4. Python `_relaunch_oom_crawl` spawns a new Node.js child in the **same container**.
5. New child's pre-flight check reports `💾 Memory status: 5.98GB / 6.00GB (99.7% used)` → exit code 3.
6. Loop repeats until `MAX_OOM_RESTARTS` is reached and the job is marked `failed`.

Root cause: this crawl uses **Camoufox** (stealth Firefox) via `camoufox: True`. The kill commands at both callsites target `chrome|chromium` (+ `playwright` at pre-flight only) — pattern does **not** match Camoufox/Firefox children. Firefox processes survive across:

- The Tier 2 Phase A recovery — Phase A reports success but memory does not drop, Phase B fires.
- The OOM_RELAUNCH boundary — the new Node.js child starts with the same Firefox children still occupying the cgroup. Pre-flight `> 80%` threshold aborts immediately.

Evidence in log:
- `[Phase A] Killing all Chrome/Playwright processes` → followed by `Memory STILL CRITICAL (93.0%) after recovery`.
- Restart pre-flight: `🧹 Checking for orphan browser processes... ✅ No orphan processes found.` (false negative — pattern did not match Camoufox).
- Pre-flight memory: `99.7% used` immediately after the supposed cleanup.

Secondary contributor: pre-flight reads cgroup memory immediately after `pkill` with no reap delay. Kernel reaping of killed processes' anonymous pages is asynchronous. Even when the pattern catches all browser children, `memory.current` lags briefly. This spec adds a 2-second delay to absorb that latency.

Page-cache contribution to `memory.current` (a third potential lever) is deferred to Spec-B.

## 2. Goals

- Widen the browser-process kill pattern so Camoufox/Firefox children are reliably killed at both callsites (pre-flight orphan cleanup + Tier 2 Phase A recovery).
- Centralise the kill logic so future engine additions (e.g., new Playwright variants, WebKit) only require one edit.
- Add a 2-second reap delay after pre-flight kill so cgroup `memory.current` reflects the post-kill state before the threshold check runs.
- Ship with a unit test that locks in the pattern composition and a smoke verification plan.

## 3. Non-Goals

- Cgroup memory-measurement correction (page-cache subtraction via `memory.stat`). Spec-B.
- Separate counters for pre-flight aborts vs Tier 2 mid-crawl aborts (P3 in the original trade-off list). Defer; revisit if Spec-A + Spec-B leave residual false-positive aborts.
- `drop_caches` privilege grant (P4). Skip — Spec-B's measurement correction obviates it without escalating container privileges.
- Watchdog poll-interval tuning (`setInterval` cadence in `main.ts`). Out of scope; current interval is sufficient.
- Python-side `_relaunch_oom_crawl` changes. Exit-code 3 contract unchanged.

## 4. Architecture

Single TypeScript file change: `apps-microservices/crawler-service/crawler/src/main.ts`. No Python, no docker-compose, no `.env`, no protos. One new test file under `apps-microservices/crawler-service/crawler/src/tests/`.

### 4.1 Components

```
crawler/src/main.ts
├── const BROWSER_KILL_PATTERN          // NEW — exported constant
├── async function killBrowserProcesses // NEW — exported helper
├── Pre-flight block (lines ~177-191)   // MODIFIED — calls helper + 2s sleep
└── handleCriticalMemory (Tier 2 Phase A, line ~333)  // MODIFIED — calls helper
```

### 4.2 Browser kill pattern

```ts
export const BROWSER_KILL_PATTERN =
    "chrome|chromium|firefox|camoufox|playwright|headless_shell";
```

Rationale per token:

| Token | Why |
|---|---|
| `chrome` | Playwright Chromium / Chrome fallback (when `camoufox=False`) |
| `chromium` | Same — explicit binary name |
| `firefox` | Camoufox is a Firefox derivative; bundled binary's process name is `firefox` |
| `camoufox` | Path-based match for `~/.cache/camoufox/...` references in cmdline |
| `playwright` | Playwright internal helper processes (e.g., `playwright-driver`) |
| `headless_shell` | Chromium headless-shell binary (used by some Crawlee versions) |

### 4.3 Kill helper

```ts
export async function killBrowserProcesses(timeoutMs = 5000): Promise<void> {
    try {
        await execAsync(
            `pkill -9 -f "${BROWSER_KILL_PATTERN}" 2>/dev/null || true`,
            { timeout: timeoutMs },
        );
    } catch (e: any) {
        if (e.code !== 'ETIMEDOUT' && e.signal !== 'SIGKILL') {
            console.warn('⚠️  killBrowserProcesses warning:', e.message);
        }
    }
}
```

Notes:
- `2>/dev/null || true` preserves current "no processes = success" semantics.
- `pkill -f` matches against full `/proc/*/cmdline`. Kernel iterates over the container's PID namespace only — does **not** cross container boundaries (no `pid: host` in compose).
- The catch block mirrors the existing log-and-continue behaviour. ETIMEDOUT / SIGKILL still suppressed because they are expected outcomes (timeout = no processes hit; SIGKILL = pkill killed itself in a corner case).

### 4.4 Pre-flight change (replaces lines ~177-191)

Current code runs two `pkill` calls + a try/catch wrapper that logs `✅ Orphan processes cleaned.` or `✅ No orphan processes found.`. Replace with:

```ts
console.log('🧹 Checking for orphan browser processes...');
await killBrowserProcesses();
// Reap delay: kernel reclaims anon pages from killed children asynchronously.
// 2s is empirically sufficient on Linux 5.x+ to flush the post-kill cgroup state
// before the threshold check below reads /sys/fs/cgroup/memory.current.
await new Promise((r) => setTimeout(r, 2000));
console.log('✅ Orphan browser processes cleaned (engines: chrome/chromium/firefox/camoufox/playwright/headless_shell).');
```

The "Orphan processes cleaned" log retains its current symbol convention. Engine list is appended for operator clarity when grep-investigating future restart-loop incidents.

### 4.5 Tier 2 Phase A change (replaces line ~333)

```ts
// Before:
console.log("   -> [Phase A] Killing all Chrome/Playwright processes");
await execAsync('pkill -9 -f "chrome|chromium" 2>/dev/null || true');

// After:
console.log("   -> [Phase A] Killing all browser processes");
await killBrowserProcesses();
```

**No 2s sleep added here.** Phase A `return`s after kill + emergency persist + double GC; the watchdog `setInterval` re-reads `memory.current` on its next tick (already several hundred ms to seconds later). Phase A's existing flow provides sufficient reap latency; an explicit sleep would only add deterministic delay to recovery without benefit.

### 4.6 Data flow

```
Pre-flight (boot):
    killBrowserProcesses() → sleep(2000) → readContainerMemory → memPercent > 80? exit(3) : continue

Tier 2 Phase A (mid-crawl, >92%):
    killBrowserProcesses() → emergency persist → double GC → return
        ↓ (next setInterval tick)
    readContainerMemory → still >92%? Phase B (graceful shutdown, exit 3) : recovery success
```

### 4.7 Backward compatibility

Pure additive widening. Every process matched by the old pattern is still matched by the new one. New matches catch Firefox/Camoufox/headless_shell — the intent. No process is killed that should survive (Node.js, Python, uvicorn, redis-cli all unaffected).

### 4.8 Blast radius

crawler-service container only. Per-replica isolation guaranteed by Docker's default PID namespace — verified via `grep` of `docker-compose.yml`: no `pid:`, no `pid_mode`, no `privileged`, no `cap_add`. Replica-A's `pkill` cannot see replica-B's PIDs.

Cgroup memory accounting is per-replica too (`/sys/fs/cgroup/memory.{max,current}` reflects only the container's own usage). No cross-replica side effects.

## 5. Testing

### 5.1 Unit test (new)

File: `apps-microservices/crawler-service/crawler/src/tests/killBrowserProcesses.test.ts`

Framework: `node:test` (per `package.json` `"test": "node --import tsx --test src/**/*.test.ts"`).

```ts
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { BROWSER_KILL_PATTERN } from '../main.js'; // adjust to actual export point

test('BROWSER_KILL_PATTERN contains all required engines', () => {
    const expected = ['chrome', 'chromium', 'firefox', 'camoufox', 'playwright', 'headless_shell'];
    for (const token of expected) {
        assert.ok(
            BROWSER_KILL_PATTERN.split('|').includes(token),
            `Pattern missing engine "${token}"`,
        );
    }
});

test('BROWSER_KILL_PATTERN has no unintended tokens', () => {
    const allowed = new Set(['chrome', 'chromium', 'firefox', 'camoufox', 'playwright', 'headless_shell']);
    for (const token of BROWSER_KILL_PATTERN.split('|')) {
        assert.ok(allowed.has(token), `Unexpected token "${token}" in pattern`);
    }
});
```

Two tests lock in the pattern composition on both sides: presence (catches accidental token removal) and exhaustiveness (catches accidental token additions that may collide with `node` / `uvicorn` / `python`).

`killBrowserProcesses` itself is **not** unit-tested directly. Mocking `execAsync` in ES-module land via `node:test` is achievable but brittle; the value over reading the helper code is marginal. Behaviour is verified via operator smoke (§5.2).

### 5.2 Operator smoke

After deploy to one dev/staging replica:

1. Start a fresh crawl that historically OOM'd (the `shop.monlabofermier.fr` case or equivalent Camoufox-using shop crawler).
2. Wait for the first OOM_RELAUNCH cycle to fire.
3. **Pre-fix expected** (today): pre-flight reports `99%+` and exits immediately. Restart loop until `MAX_OOM_RESTARTS`.
4. **Post-fix expected**: pre-flight reports a low percentage after the 2s sleep; new Node.js child starts cleanly and the crawl resumes.
5. Inspect `crawler.log` for the new pre-flight log line including the engine list — confirms the new code path is live.

Verification artefact: `crawler.log` showing pre-flight memory percentage **dropping below 80%** between successive OOM_RELAUNCH cycles. Today the log shows 99.7% repeating; after fix it should show e.g. 35-45% on the second cycle.

### 5.3 Regression scope

- Pre-existing tests under `crawler/src/tests/` (`test_functions.ts`, etc.) must keep passing — `npm test` baseline.
- `tsc` build must pass.
- No Python-side test impact.

## 6. Risks

| Risk | Mitigation |
|---|---|
| Widened pattern matches an unintended process | Manually audit `/proc/*/cmdline` inside container post-deploy. The expected set in the crawler-service container is: `node` (the crawler), `bash` (entrypoint shell wrappers), `uvicorn`/`python` (FastAPI parent), `pkill` itself transiently, Camoufox/Firefox/playwright (target). None of the non-target names contain any of the six tokens. |
| 2s sleep slows startup unnecessarily on healthy boots | Healthy boots run `pkill` against zero matches (helper returns immediately), then sleep for 2s. Container start time grows by 2s. Acceptable: container start happens at most once per crawl restart, and the alternative (no sleep) is the current bug. |
| Phase A's lack of explicit sleep means kill effect still racy with next watchdog tick | Watchdog poll interval (`setInterval` in main.ts) is sub-5-second; kernel reap usually completes in <1s after `pkill -9`. Acceptable. Empirical verification per §5.2. |
| Camoufox cache directory naming includes "camoufox" but no live process command does | The pattern matches `/proc/*/cmdline`, which includes binary path + args. Camoufox processes are launched with a path like `/root/.cache/camoufox/.../firefox`. Both `firefox` (binary name) and `camoufox` (path component) appear in cmdline. The `camoufox` token is defensive — even if `firefox` alone catches today's deployment, the extra match is cheap and protects against future package layout changes. |

## 7. Rollout

1. Single commit on `features/poc` (conventional commit, bilingual EN/FR per project convention).
2. Local: `cd apps-microservices/crawler-service/crawler && npm test && npm run build`. Both must pass.
3. Deploy: standard `docker compose` redeploy of crawler-service profile. Per-replica rolling restart acceptable; no schema migration, no Redis state change, no Python-side coordination.
4. Validate per §5.2 on one replica before scaling to all 7.
5. Push decision deferred to operator.

## 8. Out of scope for future specs

Tracked deferred items (re-evaluate after Spec-A + Spec-B ship):

- Pre-flight retry budget separation (P3 from initial trade-off list).
- Watchdog kill helper used by tooling outside crawler-service.
- Reap-delay env-var tunability (`PREFLIGHT_REAP_MS`). Default 2000ms is hardcoded; promote to env var only if production tuning reveals deviation.
- Per-engine kill metrics (count by engine) — observation-driven decision after Spec-B logging lands.

## 9. References

- `apps-microservices/crawler-service/crawler/src/main.ts:177-237` (pre-flight block)
- `apps-microservices/crawler-service/crawler/src/main.ts:321-363` (Tier 2 Phase A handler)
- `apps-microservices/crawler-service/CLAUDE.md` (Camoufox + Exit Codes sections)
- `docker-compose.yml:1336-1370` (crawler-service block — confirms no `pid: host`, no `privileged`)
- Production log: `crawler.log` for crawl id `6334` on `shop.monlabofermier.fr`
