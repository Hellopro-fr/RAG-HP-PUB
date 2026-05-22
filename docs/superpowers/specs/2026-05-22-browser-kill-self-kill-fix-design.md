# Browser Kill Self-Kill Fix — Design

**Status:** Draft
**Date:** 2026-05-22
**Author:** Rindra ANDRIANJANAKA
**Scope:** `apps-microservices/crawler-service/crawler/src/browserKill.ts` + its test

## 1. Symptom

Every Camoufox crawl freezes immediately after the pre-flight kill log line and never recovers. Observed on crawl 6735 (`atosafr.fr`) and every other Camoufox-enabled crawl since Spec-A deploy.

User-reported log (truncated at the freeze point):

```
[stdout] 🦊 Browser: Camoufox (stealth Firefox)
[stdout] Changed working directory to: /app/storage/6735
[stdout] Crawler starting with arguments: {
  "domain": "atosafr.fr", "site": "https://atosafr.fr/", "id": "6735",
  …
  "camoufox": "True"
}
[stdout] 🧹 Checking for orphan browser processes...
< freeze — no more output, crawl marked failed, Python OOM_RELAUNCH loop >
```

The crawler then enters an infinite restart loop until `MAX_OOM_RESTARTS` is hit, at which point the job goes to `failed` status. Operator-visible symptom: all Camoufox crawls stuck restarting.

## 2. Root cause

Spec-A (commit `9ab489cf`, `docs/superpowers/specs/2026-05-21-camoufox-oom-restart-loop-design.md`) introduced `BROWSER_KILL_PATTERN` in `browserKill.ts`:

```typescript
export const BROWSER_KILL_PATTERN =
    "chrome|chromium|firefox|camoufox|playwright|headless_shell";
```

The pre-flight kill runs:

```bash
pkill -9 -f "chrome|chromium|firefox|camoufox|playwright|headless_shell" 2>/dev/null || true
```

`pkill -f` matches against the **full `/proc/<pid>/cmdline`** of every process in the PID namespace, not just executable names.

The Node crawler is spawned by `app/core/crawler_manager.py:497-504` with this command (verbatim from the log dump):

```
node /app/crawler/dist/main.js --domain=atosafr.fr --site=https://atosafr.fr/ --id=6735 …
    --camoufox=True --typecrawling=link --method=auto …
```

The literal substring `camoufox` (and equivalently `--camoufox=`) appears in the Node process's own argv. `pkill -f "…camoufox…"` matches Node itself, sends SIGKILL.

Sequence per crawl:

| t | event |
|---|---|
| t+0 | Node starts, logs `🧹 Checking for orphan browser processes...` |
| t+0 | Node calls `killBrowserProcesses()` → spawns `/bin/sh -c "pkill -9 -f ..."` |
| t+ε | `pkill` scans `/proc`, finds Node (own cmdline matches `camoufox`), sends `SIGKILL` |
| t+ε | Node dies with signal SIGKILL → exit code `-9` (Linux convention `137`) |
| t+ε | Python `_monitor_process` reads exit `-9` → `_classify_exit_code(-9) → failure_cause=killed_oom_system` per current code → status=failed OR OOM_RELAUNCH (depends on classifier branch) |
| t+ε | Python's OOM relaunch path spawns NEW Node with IDENTICAL command → same self-kill → loop |

**Why Spec-A's smoke test missed it:** the manual smoke playbook (Spec-A § 7) was operator-side log inspection only and likely tested on a non-Camoufox crawl, or only verified that `✅ Orphan browser processes cleaned` appeared on a fresh container with no existing browser processes (where pkill matches nothing including Node's own argv — wait, this is wrong, pkill ALWAYS finds Node when Camoufox=True). More plausible: the smoke test used `camoufox=False` for the test crawl.

**Why Camoufox-enabled crawls were broken from Spec-A day 1:** Camoufox is the default browser per `apps-microservices/crawler-service/CLAUDE.md` § "Camoufox Default Browser". Every production crawl since Spec-A deploy has hit this self-kill. The OOM-relaunch behavior masked it for a while — operators saw "crawls failing intermittently" rather than "every Camoufox crawl fails".

## 3. Fix

Narrow `BROWSER_KILL_PATTERN` so each engine name must be preceded by `/` — matches executable filesystem paths, not arg-string substrings:

```typescript
// Before:
export const BROWSER_KILL_PATTERN =
    "chrome|chromium|firefox|camoufox|playwright|headless_shell";

// After:
export const BROWSER_KILL_PATTERN =
    "/chrome|/chromium|/firefox|/camoufox|/playwright|/headless_shell";
```

### Correctness trace

| Target process | Cmdline / executable path | Matches `/chrome` family? |
|---|---|---|
| Camoufox Firefox child | `/root/.cache/camoufox/.../firefox-bin --remote-debugging-port=…` | ✓ matches `/firefox` and `/camoufox` |
| Playwright Chromium child | `/ms-playwright/chromium-XXX/chrome-linux/chrome --no-sandbox …` | ✓ matches `/chrome` and `/chromium` |
| Playwright driver helper | `node /app/node_modules/playwright/cli.js …` | ✓ matches `/playwright` |
| Headless shell variant | `/ms-playwright/chromium-XXX/chrome-linux/headless_shell …` | ✓ matches `/headless_shell` |
| **Node crawler self (Camoufox=True)** | `node /app/crawler/dist/main.js --domain=… --camoufox=True --typecrawling=link …` | **✗ no leading `/` before `camoufox` → no match** |
| Crawlee internal helpers | `node /app/dist/…` | ✗ no match |

The fix is exact: every legitimate kill target keeps matching; the false-positive on Node's own argv is eliminated.

### Alternatives rejected

1. **Self-exclude by Node PID** (`pgrep -f "…" | grep -v $OWN_PID | xargs kill -9`). More code, more shell-quoting hazards. The leading-slash narrowing is simpler and complete.
2. **Drop `-f` flag** (match process names only, not cmdline). Process names get truncated to 15 chars; `headless_shell` is right at the limit, name match becomes fragile.
3. **Revert Spec-A to `chrome|chromium` only**. Defeats Spec-A's purpose — Camoufox/Firefox/Playwright internals were added specifically to fix the original OOM restart loop.

## 4. Components

### 4.1 `browserKill.ts` change

One-line constant update:

```typescript
export const BROWSER_KILL_PATTERN =
    "/chrome|/chromium|/firefox|/camoufox|/playwright|/headless_shell";
```

The kill invocation itself is unchanged:

```typescript
await execAsync(
    `pkill -9 -f "${BROWSER_KILL_PATTERN}" 2>/dev/null || true`,
    { timeout: timeoutMs, killSignal: 'SIGKILL' },
);
```

And the engine-list log derivation is unchanged:

```typescript
const engines = BROWSER_KILL_PATTERN.replace(/\|/g, "/");
console.log(`✅ Orphan browser processes cleaned (engines: ${engines}).`);
```

(Post-fix the log will print engines as `/chrome//chromium//firefox//camoufox//playwright//headless_shell` because `replace(/\|/g, "/")` collapses `|/` to `//`. Cosmetic — acceptable. Could be tightened to `.replace(/\|\//g, ", ")` for prettiness, but not part of this fix.)

### 4.2 Test update

`apps-microservices/crawler-service/crawler/src/tests/browserKill.test.ts` already asserts two facts about `BROWSER_KILL_PATTERN`:

1. **Presence:** each engine name (`chrome`, `chromium`, `firefox`, `camoufox`, `playwright`, `headless_shell`) appears in the pattern.
2. **Exhaustiveness:** the pattern matches the literal known engine list.

Both assertions need updating to expect leading slashes. The presence test is unchanged in spirit (each engine name is still present as a substring of the pattern — just preceded by `/`). The exhaustiveness assertion must compare the new string.

**Add one new regression test:**

```typescript
test('pattern does NOT match Node argv strings containing engine names', () => {
    const nodeArgvSample = 'node /app/crawler/dist/main.js --domain=atosafr.fr --camoufox=True --typecrawling=link';
    const regex = new RegExp(BROWSER_KILL_PATTERN);
    assert.equal(regex.test(nodeArgvSample), false,
        'pattern matched a Node argv string — would cause self-kill at pre-flight');
});

test('pattern DOES match legitimate browser executable paths', () => {
    const camoufoxPath = '/root/.cache/camoufox/playwright/firefox-bin --remote-debugging-port=12345';
    const playwrightChromePath = '/ms-playwright/chromium-1234/chrome-linux/chrome --no-sandbox';
    const playwrightDriver = 'node /app/node_modules/playwright/cli.js launch-server';
    const regex = new RegExp(BROWSER_KILL_PATTERN);
    assert.equal(regex.test(camoufoxPath), true);
    assert.equal(regex.test(playwrightChromePath), true);
    assert.equal(regex.test(playwrightDriver), true);
});
```

Locks in both the false-positive guard (the actual bug fix) and the legitimate-target coverage.

## 5. Operational rollout

1. Apply the change (1 source line + 2 test updates + 2 new tests).
2. Run `cd apps-microservices/crawler-service/crawler && npm test && npm run build`. Expect all green.
3. Deploy. Operator triggers ONE Camoufox crawl on a test domain.
4. Verify in `crawler.log`:
   - `🧹 Checking for orphan browser processes...` appears.
   - `✅ Orphan browser processes cleaned (engines: ...)` appears immediately after.
   - `💾 Memory status: ...` appears next.
   - `✅ Pre-flight checks passed. Starting crawler...` appears.
   - Crawl proceeds to fetch URLs (Crawlee logs visible).
5. Check Python `crawler-service` logs: no OOM_RELAUNCH spam, no `failure_cause=killed_oom_system` rows in `domaine_fr_retry`.
6. Optional: confirm exit code 137 / signal -9 stops appearing in `_monitor_process` exit-code logs.

## 6. Edge cases

| Case | Behavior |
|---|---|
| First crawl on fresh container | Pre-flight kill finds no matching processes → pkill returns non-zero → `\|\| true` absorbs → ✅ log fires. Same as before fix, but Node no longer self-targets. |
| OOM relaunch (Python re-spawns Node) | New Node has same `--camoufox=True` argv; pre-flight kill scans /proc, finds no orphan browser children yet (clean restart), pkill matches nothing → ✅ log. Node argv still does NOT match because no leading `/`. |
| Tier 2 Phase A recovery (within a single crawl, after browser children spawned) | pkill scans /proc, finds the Camoufox/Chromium children that opened their own executables (`/root/.cache/camoufox/...firefox-bin`, `/ms-playwright/...chrome`) → matches `/firefox`, `/camoufox`, `/chrome` → kills them. Node parent unaffected because its argv has no `/camoufox`. Exactly the recovery semantics Spec-A intended. |
| Camoufox stored at a non-default cache path | If operator overrides Camoufox cache directory (e.g. `/var/cache/camoufox/...`), the pattern `/camoufox` still matches. ✓ |
| Camoufox binary symlinked from `/usr/local/bin/camoufox` | Pattern matches the symlink path. ✓ |
| Multi-crawl scaling (multi-replica) | Each replica has its own PID namespace (Docker default). pkill in one replica cannot see Node in another replica. Unaffected. |

## 7. Files touched

```
apps-microservices/crawler-service/crawler/src/browserKill.ts                 MOD  pattern constant: prepend `/` to each engine
apps-microservices/crawler-service/crawler/src/tests/browserKill.test.ts      MOD  update existing 2 tests + add 2 regression tests
```

## 8. References

- `docs/superpowers/specs/2026-05-21-camoufox-oom-restart-loop-design.md` — Spec-A (the change being amended).
- Commit `9ab489cf` — Spec-A T1 introducing `BROWSER_KILL_PATTERN`.
- `apps-microservices/crawler-service/crawler/src/main.ts:178-184` — pre-flight callsite.
- `apps-microservices/crawler-service/app/core/crawler_manager.py:497-504` — Node spawn command construction (where `--camoufox=True` enters argv).
- `apps-microservices/crawler-service/CLAUDE.md` § "Camoufox Default Browser" — confirms `camoufox=True` is the default for every crawl.
