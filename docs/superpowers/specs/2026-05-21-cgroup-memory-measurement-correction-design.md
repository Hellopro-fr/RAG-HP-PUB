# Cgroup Memory Measurement Correction (Page-Cache Subtraction)

> **Date:** 2026-05-21
> **Status:** Approved — ready for plan writing
> **Repo:** `RAG-HP-PUB`
> **Branch:** `features/poc`
> **Service:** `apps-microservices/crawler-service`
> **Predecessor:** `docs/superpowers/specs/2026-05-21-camoufox-oom-restart-loop-design.md` (Spec-A — Camoufox kill-pattern widening + 2s reap delay; commits `9430c1ed..371ba8cd` on `features/poc`). Spec-B is the page-cache subtraction lever Spec-A § 1 deferred and Spec-A § 3 listed as non-goal.

---

## 1. Problem

Production crawler-service hit an infinite OOM_RELAUNCH loop on `shop.monlabofermier.fr` (crawl id `6334`). Spec-A's root-cause investigation identified two contributing factors:

1. **Camoufox/Firefox children survive `pkill`** — pattern `chrome|chromium` missed Firefox-based engines. **Fixed in Spec-A** (commits `9ab489cf..3ce4dc82`).
2. **Pre-flight reads `memory.current` raw** — counts page cache (which Linux reclaims on demand) as "used", inflating the percentage when the prior crawl wrote heavy I/O. **Spec-B fixes this.**

Concrete evidence: on the bug-reproducing replica, `memory.current = 5.98 GB / 6 GB = 99.7%`. After Spec-A's `pkill` widening eliminates leftover Firefox processes, the bulk of remaining `memory.current` is page cache (datasets/, request_queues/, request_urls/ writes from the prior 76-minute crawl), not anonymous RSS. Linux can reclaim that cache instantly when allocations need memory — the kernel does this routinely. But the pre-flight check at `main.ts:224` (`if (memPercent > 80)`) reads `usedMem = memory.current` and aborts.

The fix: subtract reclaimable page cache from "used" before computing the percentage. `memory.stat` exposes the `file` key (cgroup v2) / `cache` key (cgroup v1) containing the total page-cache bytes for the cgroup. Linux can reclaim all file pages (both active + inactive) before invoking the OOM-killer.

```
usableUsed = memory.current - file     (cgroup v2)
           = memory.usage_in_bytes - cache  (cgroup v1)
memPercent = (usableUsed / memory.max) * 100
```

For the bug scenario: `(5.98 - 5.40) / 6.00 = 9.7%`. Pre-flight passes, crawl resumes.

## 2. Goals

- Replace raw `memory.current` reads with a corrected formula that subtracts page-cache bytes, in both the pre-flight check and the mid-crawl watchdog.
- Centralise the cgroup-read logic in a side-effect-free `cgroupMemory.ts` module so it can be unit-tested (mirroring Spec-A's `browserKill.ts` pattern — `main.ts` has top-level side effects that block direct import in tests).
- Surface the page-cache delta in operator logs: render the memory status with both **usable** and **raw** values so future incidents have immediate diagnostic visibility.
- Keep existing threshold values (pre-flight 80%, Tier 1 85%, Tier 2 92%) unchanged numerically. Observe the production distribution under the new metric; re-tune in a separate spec if the data justifies.

## 3. Non-Goals

- Threshold re-tuning. YAGNI until production data on the new metric exists. Separate spec if needed.
- Hard ceiling on raw `memory.current / memory.max`. Rejected: any ceiling <99.7% re-fires the bug Spec-B is fixing. Trust the formula; Linux OOM-killer is the catastrophic safety net.
- `drop_caches` privilege grant. Original Spec-A § 3 non-goal — measurement correction obviates it.
- Pre-flight retry budget separation (P3 from the trade-off matrix). Defer; revisit if Spec-A + Spec-B leave residual false-positive aborts.
- Watchdog poll-interval tuning. Out of scope.
- Cross-replica or cross-service changes. Spec-B is scoped to one TypeScript file refactor + one new module + one new test.

## 4. Architecture

Three files touched:

```
apps-microservices/crawler-service/crawler/src/
├── cgroupMemory.ts                  NEW — side-effect-free module
├── main.ts                          MODIFIED — pre-flight + readContainerMemory + handler logs
└── tests/
    └── cgroupMemory.test.ts         NEW — pure parser fixture tests
```

### 4.1 `cgroupMemory.ts` — module surface

```ts
import fsPromises from 'node:fs/promises';
import os from 'node:os';

export interface UsableMemory {
    /** memory.current - file (v2) or memory.usage_in_bytes - cache (v1). */
    usableUsed: number;
    /** memory.max (v2) or memory.limit_in_bytes (v1) or os.totalmem() (host fallback). */
    totalMem: number;
    /** memory.current (v2) or memory.usage_in_bytes (v1) or os.totalmem()-os.freemem() (host fallback). */
    rawCurrent: number;
    /** file (v2) or cache (v1); 0 on host fallback (no cgroup visibility). */
    pageCache: number;
}

/**
 * Pure function. Parses a cgroup memory.stat file content and returns the
 * page-cache bytes. v2 uses the "file" key; v1 uses the "cache" key.
 * Returns { file: 0 } when neither key is present.
 * Malformed lines are skipped silently.
 */
export function parseMemoryStat(content: string): { file: number } { ... }

/**
 * Composition: reads cgroup memory.{max,current,stat} (v2 first, v1 fallback,
 * host last) and returns the usable-used view. Returns null only when all three
 * fallback paths fail (true I/O failure — never expected in a Linux Docker container).
 */
export async function readUsableMemory(): Promise<UsableMemory | null> { ... }
```

### 4.2 Lookup order inside `readUsableMemory()`

```
1. cgroup v2:
   read /sys/fs/cgroup/memory.max     → totalMem
   read /sys/fs/cgroup/memory.current → rawCurrent
   read /sys/fs/cgroup/memory.stat    → parseMemoryStat → pageCache
   if all three succeed and memory.max != "max":
       usableUsed = rawCurrent - pageCache
       return { usableUsed, totalMem, rawCurrent, pageCache }

2. cgroup v1:
   read /sys/fs/cgroup/memory/memory.limit_in_bytes → totalMem
   read /sys/fs/cgroup/memory/memory.usage_in_bytes → rawCurrent
   read /sys/fs/cgroup/memory/memory.stat → parseMemoryStat → pageCache
   if all three succeed:
       usableUsed = rawCurrent - pageCache
       return { usableUsed, totalMem, rawCurrent, pageCache }

3. Host fallback (no cgroup, e.g., local dev outside Docker):
   totalMem = os.totalmem()
   rawCurrent = os.totalmem() - os.freemem()
   pageCache = 0  (no visibility from os.* APIs)
   usableUsed = rawCurrent  (same as raw — no correction possible)
   return { usableUsed, totalMem, rawCurrent, pageCache }

4. If all fail (exception thrown by every readFile + os.*):
   return null
```

### 4.3 `main.ts` pre-flight refactor (current lines 189-231)

Replace the inline cgroup-reading block with:

```ts
const mem = await readUsableMemory();
if (!mem) {
    // Cannot measure memory. Skip pre-flight — assume OK rather than block startup.
    console.warn('⚠️  Pre-flight: readUsableMemory() returned null. Skipping threshold check.');
} else {
    const usablePercent = (mem.usableUsed / mem.totalMem) * 100;
    const rawPercent = (mem.rawCurrent / mem.totalMem) * 100;
    console.log(
        `💾 Memory status: ${gb(mem.usableUsed)}GB usable / ${gb(mem.rawCurrent)}GB raw / ` +
        `${gb(mem.totalMem)}GB limit ` +
        `(${usablePercent.toFixed(1)}% usable, ${rawPercent.toFixed(1)}% raw, ${gb(mem.pageCache)}GB page cache).`
    );
    if (usablePercent > 80) {
        console.error(`❌ Memory critically low: ${usablePercent.toFixed(1)}% usable used. Aborting to prevent OOM.`);
        console.error(`🔄 Pre-flight OOM: exiting with code 3 (OOM_RELAUNCH) to trigger Python-side auto-restart.`);
        process.exit(3);
    }
}
```

Where `gb(n)` is `(n / 1024 / 1024 / 1024).toFixed(2)` — extract to a local lambda or import from a util. Existing code already does this inline at lines 222, 226 — opportunity to DRY (small scope, acceptable).

The `containerMemoryMb` constant at line 237 (`Math.floor(totalMem / 1024 / 1024)`) — preserve. It is used downstream to inform Crawlee's autoscaler. After refactor it reads from `mem.totalMem`.

### 4.4 `main.ts` watchdog refactor (`readContainerMemory`, current lines 239-270)

Two options for shape compatibility. **Pick the adapter pattern** to keep Tier 1/2 handler signatures unchanged:

```ts
const readContainerMemory = async (): Promise<{ usedMem: number; totalMem: number } | null> => {
    const mem = await readUsableMemory();
    if (!mem) return null;
    return { usedMem: mem.usableUsed, totalMem: mem.totalMem };
};
```

`usedMem` semantics shift from "raw `memory.current`" to "usable used". Threshold values (85, 92) keep the same numeric meaning — they now reflect anon+slab+kernel pressure, not page-cache occupancy.

### 4.5 Tier 1 + Tier 2 handler log lines

`handleWarningMemory` (around line 278) and `handleCriticalMemory` (around line 315) log the memory percent in their entry messages. After refactor, those percents reflect usable%. Update the log strings to be explicit:

- Tier 1: `⚠️  [Tier 1] Memory Warning (${memPercent.toFixed(1)}% usable). executing proactive recovery...`
- Tier 2: `❌ [Tier 2] Memory CRITICAL (${memPercent.toFixed(1)}% usable). Initiating Phase A Recovery...`
- Tier 2 Phase B retry: `❌ [Tier 2] Memory STILL CRITICAL (${memPercent.toFixed(1)}% usable) after recovery. Initiating Phase B: Auto-Relaunch...`

The "% usable" suffix is the only string change; existing emoji/format preserved.

### 4.6 Data flow

```
Pre-flight (boot):
    killBrowserProcesses() [Spec-A]
    → sleep(2s) [Spec-A]
    → readUsableMemory()
    → (usableUsed/totalMem > 80%)? exit(3) : continue

Watchdog setInterval:
    readContainerMemory() → readUsableMemory() with shape adapter
    → (usable% > 92%)? Tier 2 Phase A : (usable% > 85%)? Tier 1 : continue
```

### 4.7 Backward compatibility

- Threshold numeric values unchanged. Old metric included page cache; new doesn't. Same number = more tolerant in practice.
- Log line format changes. Confirmed no Prometheus / Grafana scrape on the old `💾 Memory status: ...` line. Compose configs under `grafana/` + `prometheus/` checked; no consumer.
- Crawlee's autoscaler `memoryMbytes` config (informed by `containerMemoryMb` at main.ts:237) preserved — `totalMem` semantics unchanged.
- Spec-A's `killBrowserProcesses()` helper + 2-second reap delay stay untouched.

### 4.8 Blast radius

crawler-service container only. Per-replica isolation guaranteed (Docker default PID namespace + per-container cgroup hierarchy — verified during Spec-A's audit).

## 5. Testing

### 5.1 Unit tests (new) — `cgroupMemory.test.ts`

Framework: `node:test` (per `package.json` `"test": "node --import tsx --test src/**/*.test.ts"`).

Four pure-function tests on `parseMemoryStat`:

1. **cgroup v2 format** — input contains `file 5800000000\n`, parser returns `{ file: 5800000000 }`.
2. **cgroup v1 format** — input contains `cache 5800000000\n`, parser returns `{ file: 5800000000 }` (parser normalises v1's `cache` key to the `file` field of the return).
3. **Missing key** — input has neither `file` nor `cache` lines, parser returns `{ file: 0 }`.
4. **Malformed lines** — input includes blank lines, lines with extra whitespace, lines with non-numeric values; parser skips them without throwing and still extracts a valid `file` key when present.

`readUsableMemory()` composition is **not** unit-tested directly. Mocking `node:fs/promises` in ES-module land via `node:test`'s mock APIs is brittle. The composition is glue + I/O; verification happens via operator smoke (§5.2). The pure parser carries the only complexity worth unit-testing.

### 5.2 Operator smoke

After deploy to one dev/staging replica:

1. Inspect `crawler.log` of any newly-started crawl. The pre-flight log line should now show two percentages: usable (low — well below 80% in a clean container) and raw (variable — high if heavy prior I/O).
2. Cross-check `pageCache` value against `/proc/meminfo` (`Cached:` line) or `cat /sys/fs/cgroup/memory.stat | grep ^file` inside the container. They should be of the same order of magnitude (some skew expected because `/proc/meminfo` is host-wide, `memory.stat` is cgroup-scoped).
3. On a replica that historically hit the OOM_RELAUNCH loop (post-`shop.monlabofermier.fr`), restart the crawler. Pre-flight should now pass with `usablePercent < 80%` even when raw is high.
4. Trigger a heavy Tier 2 event manually if feasible (allocate-and-retain in a debug script, or wait for a normal heavy crawl). Tier 2 log line should show `usable` suffix and the threshold should fire on usable%, not raw%.

Verification artefact: a `crawler.log` excerpt with the new dual-format line on a replica known to have had high `memory.current` from a prior crawl, demonstrating the gap between `usable` (low, well below 80%) and `raw` (high, near 100%).

### 5.3 Regression scope

- `npm test`: existing 54 tests + 4 new = 58 must pass.
- `npm run build`: tsc clean.
- No Python-side impact.

## 6. Risks

| Risk | Mitigation |
|---|---|
| Subtracting all `file` over-counts reclaim capacity; sudden anon allocation spike OOMs before kernel reclaim catches up | Spec-A's 2-second reap delay after pre-flight kill absorbs the cold-start window. Tier 2 fires at 92% usable — gives Phase A recovery time before kernel OOM intervention. Linux OOM-killer is the final safety net at the catastrophic case. |
| `memory.stat` keys differ on exotic kernel versions | Parser tolerates missing keys → returns `{ file: 0 }` → `usableUsed = rawCurrent` (degrades to current behaviour, not worse). |
| Log line format change breaks an external scraper | Verified: no Prometheus / Grafana consumer scrapes the pre-flight or watchdog stdout lines. If a hidden consumer exists, it would silently fail to parse — operator-discoverable, not silently wrong. |
| `containerMemoryMb` (line 237) used by Crawlee autoscaler shifts semantics | No — `totalMem` semantics are identical (`memory.max` in v2). Only `usedMem` semantics shift; autoscaler reads `totalMem` only. |
| Real OOM masked by formula | Watchdog's 85% and 92% thresholds still trigger on legitimate anon+slab pressure. Kernel OOM-killer is the final guard. |

## 7. Rollout

1. Single feature commit on `features/poc` for the new module + test + main.ts refactor. Bilingual EN+FR conventional commit per `.claude/rules/commit-messages.md`.
2. Local verification: `cd apps-microservices/crawler-service/crawler && npm test && npm run build`. Both must pass.
3. Deploy: standard `docker compose` redeploy of `crawling` profile. No schema migration, no Redis state change, no Python-side coordination.
4. Validate per §5.2 on one replica before scaling to remaining 6.
5. Push decision deferred to operator (matches Spec-A pattern).

## 8. Out of scope for future specs

- Threshold re-tuning based on production distribution under the new metric.
- Prometheus counter for `pageCache_bytes` and `usableUsed_bytes` (separate observability spec — only if grep-based log parsing turns out insufficient).
- Memory pressure gauge (kernel `PSI` `/proc/pressure/memory`) — alternative signal, separate trade-off.
- Adaptive thresholds per crawl (depending on whether `dropData=true` or update mode) — depends on data, defer.

## 9. References

- `apps-microservices/crawler-service/crawler/src/main.ts:189-231` (pre-flight block — current)
- `apps-microservices/crawler-service/crawler/src/main.ts:239-270` (`readContainerMemory` — current)
- `apps-microservices/crawler-service/crawler/src/main.ts:278-312` (Tier 1 handler — log line target)
- `apps-microservices/crawler-service/crawler/src/main.ts:314-358` (Tier 2 handler — log line target)
- Spec-A: `docs/superpowers/specs/2026-05-21-camoufox-oom-restart-loop-design.md`
- Linux cgroup v2 memory controller docs: https://docs.kernel.org/admin-guide/cgroup-v2.html#memory-interface-files
- Production log: `crawler.log` for crawl id `6334` on `shop.monlabofermier.fr` (99.7% memory.current loop)
