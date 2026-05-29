# Browser Kill Self-Kill Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop every Camoufox crawl from self-killing at pre-flight by narrowing `BROWSER_KILL_PATTERN` to match executable filesystem paths (engine names preceded by `/`) instead of arg-string substrings.

**Architecture:** One-line constant change in `browserKill.ts` (`"chrome|chromium|..."` → `"/chrome|/chromium|..."`). Update the 2 existing presence/exhaustiveness tests to expect the new slashed tokens. Add 2 regression tests: one proving Node argv with `--camoufox=True` does NOT match the pattern (the actual bug guard), one proving real browser executable paths DO match (coverage preservation).

**Tech Stack:** TypeScript, Node 22 `node --import tsx --test` framework.

---

## Plan-level test commands

| Command | Expected |
|---|---|
| `cd apps-microservices/crawler-service/crawler && npm test -- src/tests/browserKill.test.ts` | 4 passed (2 updated + 2 new) |
| `cd apps-microservices/crawler-service/crawler && npm test` | full suite green (no regression in 82 prior tests) |
| `cd apps-microservices/crawler-service/crawler && npm run build` | tsc clean |

---

## Task 1: Narrow `BROWSER_KILL_PATTERN` to match executable paths only

**Goal:** Fix the self-kill regression by prepending `/` to each engine name in the pattern. Update the 2 existing tests and add 2 regression tests covering the false-positive guard + the legitimate-target match.

**Files:**
- Modify: `apps-microservices/crawler-service/crawler/src/browserKill.ts:18-19`
- Modify: `apps-microservices/crawler-service/crawler/src/tests/browserKill.test.ts:5-24`

**Acceptance Criteria:**
- [ ] `BROWSER_KILL_PATTERN` becomes `"/chrome|/chromium|/firefox|/camoufox|/playwright|/headless_shell"` (each engine prefixed with `/`).
- [ ] Existing "contains all required engines" test updated to compare against slashed tokens — passes.
- [ ] Existing "has no unintended tokens" test updated to allow slashed tokens — passes.
- [ ] New regression test "pattern does NOT match Node argv" — passes (proves the actual bug fix).
- [ ] New regression test "pattern DOES match browser executable paths" — passes (proves coverage preserved).
- [ ] Full suite `npm test` green: 4 browserKill tests + 78 other tests = 82 total.
- [ ] `npm run build` clean (no tsc errors — type signatures unchanged).

**Verify:** `cd apps-microservices/crawler-service/crawler && npm test && npm run build`

**Steps:**

- [ ] **Step 1: Update the test file FIRST (TDD red phase)**

Path: `apps-microservices/crawler-service/crawler/src/tests/browserKill.test.ts`

Replace the entire file with:

```typescript
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { BROWSER_KILL_PATTERN } from '../browserKill.js';

test('BROWSER_KILL_PATTERN contains all required engines (slashed form)', () => {
    const expected = ['/chrome', '/chromium', '/firefox', '/camoufox', '/playwright', '/headless_shell'];
    const tokens = BROWSER_KILL_PATTERN.split('|');
    for (const token of expected) {
        assert.ok(
            tokens.includes(token),
            `Pattern missing engine "${token}". Got: "${BROWSER_KILL_PATTERN}"`,
        );
    }
});

test('BROWSER_KILL_PATTERN has no unintended tokens (slashed form only)', () => {
    const allowed = new Set(['/chrome', '/chromium', '/firefox', '/camoufox', '/playwright', '/headless_shell']);
    for (const token of BROWSER_KILL_PATTERN.split('|')) {
        assert.ok(
            allowed.has(token),
            `Unexpected token "${token}" in pattern — could kill non-browser processes`,
        );
    }
});

test('pattern does NOT match Node argv strings containing engine names', () => {
    // Regression guard for the self-kill bug: Node's own argv contains
    // "--camoufox=True" but has NO leading "/" before "camoufox", so the
    // path-anchored pattern must not match.
    const nodeArgvSamples = [
        'node /app/crawler/dist/main.js --domain=atosafr.fr --camoufox=True --typecrawling=link',
        'node /app/crawler/dist/main.js --site=https://x --camoufox=False',
        'node /app/crawler/dist/main.js --domain=playwright-test.com --camoufox=True',
    ];
    const regex = new RegExp(BROWSER_KILL_PATTERN);
    for (const argv of nodeArgvSamples) {
        assert.equal(
            regex.test(argv),
            false,
            `pattern matched Node argv string — would cause self-kill at pre-flight: "${argv}"`,
        );
    }
});

test('pattern DOES match legitimate browser executable paths', () => {
    const legitimateTargets = [
        '/root/.cache/camoufox/playwright/firefox-bin --remote-debugging-port=12345',
        '/ms-playwright/chromium-1234/chrome-linux/chrome --no-sandbox --headless',
        '/ms-playwright/chromium-1234/chrome-linux/headless_shell --user-data-dir=/tmp/x',
        'node /app/node_modules/playwright/cli.js launch-server',
    ];
    const regex = new RegExp(BROWSER_KILL_PATTERN);
    for (const target of legitimateTargets) {
        assert.equal(
            regex.test(target),
            true,
            `pattern failed to match legitimate browser target: "${target}"`,
        );
    }
});
```

- [ ] **Step 2: Run tests, confirm they fail (TDD red)**

```bash
cd apps-microservices/crawler-service/crawler && npm test -- src/tests/browserKill.test.ts 2>&1 | tail -20
```

Expected: 4 tests run. The first two FAIL because the current pattern tokens are `chrome`/`chromium`/etc (no leading slash), so `tokens.includes('/chrome')` returns false. The third FAILS because the current pattern matches `--camoufox=True` (camoufox substring). The fourth may pass or fail depending on path match — but at least one of the four must fail to confirm we're in the red phase.

- [ ] **Step 3: Apply the pattern fix in `browserKill.ts` (TDD green phase)**

Path: `apps-microservices/crawler-service/crawler/src/browserKill.ts`

Locate lines 18-19:

```typescript
export const BROWSER_KILL_PATTERN =
    "chrome|chromium|firefox|camoufox|playwright|headless_shell";
```

Replace with:

```typescript
export const BROWSER_KILL_PATTERN =
    "/chrome|/chromium|/firefox|/camoufox|/playwright|/headless_shell";
```

Do NOT touch any other line in `browserKill.ts`. The `killBrowserProcesses` function body and the engine-log derivation (`.replace(/\|/g, "/")`) stay byte-for-byte identical.

- [ ] **Step 4: Re-run tests, confirm green**

```bash
cd apps-microservices/crawler-service/crawler && npm test -- src/tests/browserKill.test.ts 2>&1 | tail -15
```

Expected: 4 passed.

- [ ] **Step 5: Run full Node suite for regression**

```bash
cd apps-microservices/crawler-service/crawler && npm test && npm run build
```

Expected: full suite green (82 tests total — 4 browserKill + 78 others); tsc clean.

- [ ] **Step 6: Commit**

Ask user for commit language first (per project rule). Write `.git/COMMIT_EDITMSG` via the Write tool (UTF-8) — never via shell heredoc. Then:

```bash
git add apps-microservices/crawler-service/crawler/src/browserKill.ts apps-microservices/crawler-service/crawler/src/tests/browserKill.test.ts
git -c commit.encoding=utf-8 commit -F .git/COMMIT_EDITMSG
```

Commit message body (bilingual):

```
fix(crawler): browser kill pattern self-kill regression

EN:
BROWSER_KILL_PATTERN now requires a leading "/" before each engine name
(/chrome|/chromium|/firefox|/camoufox|/playwright|/headless_shell). The
previous pattern (chrome|chromium|firefox|camoufox|playwright|headless_
shell) matched the Node crawler's own argv because every Camoufox crawl
passes "--camoufox=True", causing pkill -9 -f to SIGKILL Node at pre-
flight → exit -9 → infinite OOM_RELAUNCH loop. The path-anchored
pattern still matches all legitimate browser children
(Camoufox /root/.cache/camoufox/firefox-bin, Playwright /ms-playwright/
chromium-XXX/chrome, etc.) but no longer matches arg-string substrings
in Node argv. 2 existing tests updated + 2 regression tests added.
Spec 2026-05-22 browser-kill-self-kill-fix.

FR:
BROWSER_KILL_PATTERN exige desormais un "/" avant chaque nom de moteur
(/chrome|/chromium|/firefox|/camoufox|/playwright|/headless_shell). Le
pattern precedent (chrome|chromium|firefox|camoufox|playwright|headless_
shell) matchait l'argv du crawler Node lui-meme car chaque crawl
Camoufox passe "--camoufox=True", ce qui causait pkill -9 -f a envoyer
SIGKILL a Node au pre-flight -> exit -9 -> boucle OOM_RELAUNCH infinie.
Le pattern path-ancre matche toujours tous les enfants browser
legitimes (Camoufox /root/.cache/camoufox/firefox-bin, Playwright /ms-
playwright/chromium-XXX/chrome, etc.) mais ne matche plus les sous-
chaines d'arguments dans l'argv de Node. 2 tests existants mis a jour
+ 2 tests de regression ajoutes. Spec 2026-05-22 browser-kill-self-
kill-fix.
```

---

## Self-review checklist

| Spec § | Requirement | Task |
|---|---|---|
| § 3 | Change pattern to `/chrome|/chromium|/firefox|/camoufox|/playwright|/headless_shell` | T1 Step 3 |
| § 4.1 | `browserKill.ts` constant updated; kill invocation + log derivation untouched | T1 Step 3 |
| § 4.2 | Existing 2 tests updated to expect slashed tokens | T1 Step 1 (replaces full test file) |
| § 4.2 | New regression test: pattern does NOT match Node argv | T1 Step 1 (test 3) |
| § 4.2 | New regression test: pattern DOES match browser executable paths | T1 Step 1 (test 4) |
| § 5 | Operator smoke-test playbook (deploy + trigger Camoufox crawl + verify logs) | Out-of-band — operator follows § 5 narrative post-deploy |
| § 6 | Edge cases (fresh start, OOM relaunch, Tier 2 recovery, multi-replica) | Implicit — pattern correctness covered by Test 4 (covers Tier 2 / browser children); Test 3 covers self-kill guard; multi-replica handled by Docker PID namespace (no code path needed). |

**Placeholder scan:** none — all code blocks present, all paths exact, all expected outputs concrete.

**Type consistency:** `BROWSER_KILL_PATTERN` is the only identifier; its export signature is unchanged (still `export const ... : string` via inference). Tests import it from `'../browserKill.js'` — same path as before.

**Spec coverage:** complete. No requirements missing a task.
