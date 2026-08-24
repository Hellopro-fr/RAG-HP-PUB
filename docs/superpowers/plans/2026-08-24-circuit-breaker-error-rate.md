# Circuit Breaker Error Rate — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the update-mode error-rate breaker decide on an actual proportion, so it stops creating permanently-locked domains out of runs it stopped on a number greater than 100%.

**Architecture:** Extract the inline rate computation from `routes.ts` into a pure, unit-tested `errorRateBreaker.ts`, mirroring the `externalRedirectBreaker.ts` / `terminalFailure.ts` precedent. The denominator becomes `processed + errors_unprocessed`, where a **new counter** isolates the half of `errors` that never reached `increment("processed")`. The sample gate deliberately stays on `processed`.

**Tech Stack:** TypeScript / Node 20, `node:test` runner (`npm test`), Redis-backed `StatsManager`. No framework. Production runs on a remote VM — delivery is by the repo's CI/CD, **not** an SFTP package.

**Spec:** `docs/superpowers/specs/2026-08-24-circuit-breaker-error-rate-design.md`. Read §2.1, §5 and §6 before starting. **Task 1 corrects two claims in it** — do Task 1 first, then re-read.

**User decisions (already made):**
- *"Nous allons partir sur ta recommendation"* (2026-08-24) — the §4 composition measurement is **NOT** run: no `/unstash`, no `/results`. The fix ships justified by the 12 impossible rates alone.
- The threshold (`maxErrorRate = 0.15`) is **not** touched — spec §5, out of scope.
- The user controls push and deployment. **Never push.**

---

## Global Constraints

- **Work in a worktree.** Permanent user rule: any change destined for a commit is made in a worktree created by `EnterWorktree`, never `git worktree add`. Several sessions share these repos.
- **Never `git add -A`.** Stage named files only.
- ⚠ **`npm install` fails on this repo** (`better-sqlite3` / VS Build Tools). Use `npm install --ignore-scripts`. **This bites in every fresh worktree** — `node_modules` is not carried over.
- **Baseline, derived by execution on 2026-08-24 before this plan was written:** `tests 435 / pass 435 / fail 0`, 3 suites, ~52 s. Every task's expected count is `435 + (tests you actually wrote)`. If your arithmetic and the runner disagree, **the runner is right** — an expected count that is not derived from a run is worthless.
- **Commit messages bilingual EN then FR**, per the repo's own `CLAUDE.md`.
- ⚠ **Do not touch `errors` itself.** `statNameParity.test.ts:66` records why: *"this branch must never touch `errors`: it feeds the BO health guard and both deletion caps"*. This lot adds a counter and changes a **denominator**; the meaning of `errors` is a downstream contract.

---

## What the exploration established (read this before Task 2)

Three findings from tracing the counters on 2026-08-24. They are the reason this plan is not the one-line change the spec's §5 implied.

**1. `increment("processed")` has exactly ONE writer** — `routes.ts:444`. The denominator is therefore fully characterised by that single site.

**2. `errors` has exactly TWO live writers in update mode, and they are of OPPOSITE natures.** The other two candidate writers are inert:

| Site | Fires when | Reaches `processed`? |
|---|---|---|
| `UpdateChecker.ts:175` (CASE 1) | dataset URL, HTTP ≥ 400 or status 0 | **NO** — `routes.ts:436` throws first, or the request died in `failedRequestHandler` (`functions.ts:590`) | 
| `UpdateChecker.ts:278` (CASE 3) | dataset URL, 2xx, same URL, no longer eligible (extension / param / **non-French**) | **YES** — called from `routes.ts:946` and `:1328`, both after `:444` |
| `routes.ts:408` | needs `is_existing` **and** no `updateChecker` | inert in update mode |
| `functions.ts:648` | needs `is_existing` | inert — see below |

⚠ **`is_existing` is never true.** Its only assignment is `main.ts:1033` → `false`, and `tests/seeding.dedup.test.ts:45` documents it: *"`is_existing` is never set on consolidated seeds"*. Checked by two independent search forms. A double-count of the numerator was hypothesised here and **refuted** — do not re-propose it.

**3. Therefore the spec's "symétrie exacte avec le mur de proxy" is FALSE, and copying that shape would introduce a second defect.** Both neighbouring breakers have a numerator **disjoint from `processed` by construction** — `shouldTripProxyWall(blocked, blocked + processedOk, …)`, `shouldTripExternalRedirectBreaker(external, processed, …)`. `errors` is a **mixture**. So:

```
errors      = e_off (CASE 1, never in processed) + e_on (CASE 3, already in processed)
attempts    = processed + e_off          <- correct
processed + errors                        <- over-counts by e_on
```

Writing `errors + processed` would dilute the rate for exactly the runs whose rate is already correct (the all-`not_eligible` case), i.e. it would **weaken a working guard** to fix a broken one. Hence the new counter.

**Invariant this design buys:** every `e_on` error is a URL already inside `processed`, so `errors ≤ processed + e_off = attempts` and **the rate can no longer exceed 1**. A rate above 1 becomes a counter bug, not a bad site. Spec §6 asks for exactly this and Task 2 pins it.

---

## File Structure

| File | Status | Responsibility |
|---|---|---|
| `docs/superpowers/specs/2026-08-24-circuit-breaker-error-rate-design.md` | Modify | Design authority — two corrections (Task 1) |
| `crawler/src/errorRateBreaker.ts` | **Create** | The pure decision. No Crawlee, no Redis. |
| `crawler/src/errorRateBreaker.test.ts` | **Create** | Pins the invariant, both §4.2 bounds, and the gate |
| `crawler/src/class/UpdateChecker.ts` | Modify (~`:175`) | Writes the new counter next to the off-book `errors` |
| `crawler/src/errorsUnprocessedParity.test.ts` | **Create** | Pins that the written name is the read name |
| `crawler/src/routes.ts` | Modify (`:449-467`) | Wiring only — no arithmetic left inline |
| `apps-microservices/crawler-service/CLAUDE.md` | Modify (after `## Update Mode`, ~`:83`) | The missing circuit-breaker section (spec §7) |

All paths under `crawler/src/` are relative to `apps-microservices/crawler-service/`.

---

## Task 1: Correct the spec before implementing from it

**Goal:** Remove the one false claim in the design authority and record the two findings the implementer needs, so nobody builds `errors + processed` from the letter of §5.

**Files:**
- Modify: `docs/superpowers/specs/2026-08-24-circuit-breaker-error-rate-design.md` (§5, and a new §8)

**Acceptance Criteria:**
- [ ] §5 no longer claims exact symmetry with the proxy wall; it names the mixture and the new counter
- [ ] A new §8 records that `updateHealthVerdict.ts:69` carries the **same** defect and is deliberately **out of scope**, with the reason
- [ ] §8 states the honest limitation: this fix stops the **lock**, it does not by itself make the marginal runs' deletions apply
- [ ] No claim in the spec now contradicts the "What the exploration established" section of this plan

**Verify:** `grep -c 'symétrie exacte' docs/superpowers/specs/2026-08-24-circuit-breaker-error-rate-design.md` → `0`

**Steps:**

- [ ] **Step 1: Replace the false symmetry claim in §5**

Find this sentence in §5 and replace it:

> Par symétrie exacte avec le mur de proxy du même fichier — même défaut, même remède, déjà écrit.

with:

```markdown
⚠ **La symétrie avec le mur de proxy n'est PAS exacte** — la première rédaction de cette spec
l'affirmait, à tort. Les deux disjoncteurs voisins ont un numérateur **disjoint de `processed`
par construction** (`shouldTripProxyWall(blocked, blocked + processedOk, …)`,
`shouldTripExternalRedirectBreaker(external, processed, …)`). `errors` est un **mélange** :
`UpdateChecker.ts:175` (erreur HTTP) contourne `processed`, `UpdateChecker.ts:278` (2xx non
éligible) y est **déjà compté**. Écrire `processed + errors` diluerait donc le taux précisément
sur les runs dont le taux est déjà juste — cela affaiblirait une garde qui fonctionne pour en
réparer une qui est cassée. Le dénominateur est `processed + errors_unprocessed`, un **nouveau
compteur** qui n'isole que la moitié hors-livre.
```

- [ ] **Step 2: Append §8**

```markdown
---

## 8. Ce que ce lot ne répare pas, et qu'il faut savoir avant de le lire comme un succès

### 8.1 Le MÊME défaut vit dans le verdict de santé — hors périmètre, à dessein

`updateHealthVerdict.ts:69` calcule `errorRate: stats.processed > 0 ? stats.errors / stats.processed : 0`
— **le même dénominateur défectueux**, sur le même couple de compteurs. Ce taux part dans
`_update_report.json`, que `script_process_update_crawling.php` lit par clé, et il décide du statut
`CRITICAL` qui gouverne les plafonds de suppression du BO.

**Il n'est délibérément pas corrigé ici**, pour trois raisons :

1. Le corriger **desserrerait** la détection de `CRITICAL` — moins de verdicts critiques, donc plus
   d'actions destructives appliquées. C'est une décision produit, pas un calibrage.
2. Le lot du 2026-08-17 a rendu ce module *prouvablement non régressif* avec 16 tests, dont un
   (`updateHealthRates matches the pre-change definitions`) **épingle explicitement la formule
   actuelle**. La changer, c'est changer un contrat épinglé exprès.
3. Le disjoncteur, lui, ne décide de rien d'utile : un run arrêté sur 722 % n'est pas protégé, il
   est tiré au sort. Les deux défauts sont arithmétiquement identiques et leurs **enjeux sont
   opposés**.

### 8.2 Conséquence : ce lot tarit le VERROU, pas le blocage des suppressions

Un run marginal qui ne s'arrête plus va **se terminer**. Il n'écrit alors plus de ligne `FAILED`,
donc plus de verrou permanent via `est_domaine_deja_en_cours()` — **c'est le gain, et c'est le
préjudice rapporté**. Mais son rapport portera toujours le taux calculé à l'ancienne
(§8.1) : si ce taux dépasse 15 %, le verdict reste `CRITICAL` et le BO retient les actions
destructives. ⇒ **Le domaine cesse d'être verrouillé ; ses suppressions ne s'appliquent pas pour
autant.** Annoncer « les 23 runs marginaux sont récupérés » serait faux.

⚠ À vérifier côté BO avant toute communication sur ce point : que `CRITICAL` retient bien les
actions (et non seulement `PENDING_SAMPLE`). Non vérifié à la date de cette spec.
```

- [ ] **Step 3: Verify**

Run: `grep -c 'symétrie exacte' docs/superpowers/specs/2026-08-24-circuit-breaker-error-rate-design.md`
Expected: `0`

Run: `grep -c 'updateHealthVerdict.ts:69' docs/superpowers/specs/2026-08-24-circuit-breaker-error-rate-design.md`
Expected: `1` or more

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/specs/2026-08-24-circuit-breaker-error-rate-design.md
git commit -F - <<'MSG'
docs(crawler-service): the proxy-wall symmetry the spec invoked does not hold

`errors` mixes two natures: an HTTP error bypasses `processed`, a 2xx
not-eligible verdict is already counted in it. Both neighbouring breakers
have a numerator disjoint from `processed` by construction, so copying their
shape would dilute the rate for the runs whose rate is already correct.
Records the identical defect in updateHealthVerdict.ts:69 as deliberately
out of scope, and the limitation that follows: this lot stops the lock, not
the withholding of deletions.

FR — la symétrie avec le mur de proxy invoquée par la spec ne tient pas

`errors` mélange deux natures : une erreur HTTP contourne `processed`, un
verdict 2xx non éligible y est déjà compté. Les deux disjoncteurs voisins ont
un numérateur disjoint de `processed` par construction : copier leur forme
diluerait le taux des runs dont le taux est déjà juste. Consigne le défaut
identique de updateHealthVerdict.ts:69 comme hors périmètre assumé, et la
limite qui en découle : ce lot tarit le verrou, pas la retenue des
suppressions.
MSG
```

---

## Task 2: The pure decision module

**Goal:** A dependency-free `shouldTripErrorRateBreaker()` whose rate provably cannot exceed 1, which reproduces today's verdict for every run that is legitimately stopped today, and whose tests encode both bounds of spec §4.2.

**Files:**
- Create: `apps-microservices/crawler-service/crawler/src/errorRateBreaker.ts`
- Create: `apps-microservices/crawler-service/crawler/src/errorRateBreaker.test.ts`

**Acceptance Criteria:**
- [ ] `shouldTripErrorRateBreaker` is pure — no import of Crawlee, Redis, `StatsManager` or `context`
- [ ] The sample gate reads `stats.processed`, **not** `attempts` (a test pins this)
- [ ] `maxErrorRate = 0` disables the signal (preserves `routes.ts:467`'s `> 0` semantics)
- [ ] The comparison stays strict `>` (preserves today's boundary behaviour)
- [ ] `reason` still begins with the literal `Error rate too high (` — the production log line is grepped by that prefix, and the 69-run measurement depended on it
- [ ] A zero denominator yields rate `0`, never `NaN`
- [ ] Both §4.2 bounds are separate tests: all-off-book (rescued) and all-on-book (still trips)
- [ ] `npm test` green, count = 435 + the number of tests written

**Verify:** `cd apps-microservices/crawler-service/crawler && npm test` → `fail 0`, and `tests` = 435 + tests added

**Steps:**

- [ ] **Step 1: Write the failing test file**

Create `apps-microservices/crawler-service/crawler/src/errorRateBreaker.test.ts`:

```ts
/**
 * Tests for shouldTripErrorRateBreaker().
 *
 * This breaker had NO test, which is how it shipped a "rate" that production
 * observed at 722%. The cases below are derived from the 69 stopped runs of the
 * 2026-08-10 batch (spec §1) — a rate is reproduced by a (errors, processed)
 * pair that yields it, not by the run's own raw counters, which are archived.
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { shouldTripErrorRateBreaker } from './errorRateBreaker.js';

const CFG = { minSample: 50, maxErrorRate: 0.15 };

test('the impossible rate becomes a proportion: 722% measured → 87.8%', () => {
    // 361/50 = 722%, the maximum over the 69 runs. All errors off-book.
    const r = shouldTripErrorRateBreaker(
        { errors: 361, processed: 50, errorsUnprocessed: 361 },
        CFG,
    );
    assert.equal(r.attempts, 411);
    assert.ok(r.rate <= 1, `rate must be a proportion, got ${r.rate}`);
    assert.equal((r.rate * 100).toFixed(1), '87.8');
    assert.equal(r.trip, true); // still far above 15% — the fix does not rescue this one
});

test('the rate can NEVER exceed 1, whatever the mixture', () => {
    // e_on <= processed is the invariant; sweep the whole legal space.
    for (let processed = 0; processed <= 40; processed += 8) {
        for (let eOff = 0; eOff <= 40; eOff += 8) {
            for (let eOn = 0; eOn <= processed; eOn += 4) {
                const r = shouldTripErrorRateBreaker(
                    { errors: eOff + eOn, processed, errorsUnprocessed: eOff },
                    { minSample: 0, maxErrorRate: 0.15 },
                );
                assert.ok(
                    r.rate <= 1,
                    `rate ${r.rate} > 1 for processed=${processed} eOff=${eOff} eOn=${eOn}`,
                );
            }
        }
    }
});

test('§4.2 UPPER bound — marginal run, all errors off-book: 15.2% → 13.2%, no trip', () => {
    // douillet-agricole.fr shape: stopped at 15.2% after storing 262 files.
    const r = shouldTripErrorRateBreaker(
        { errors: 40, processed: 263, errorsUnprocessed: 40 },
        CFG,
    );
    assert.equal((r.rate * 100).toFixed(1), '13.2');
    assert.equal(r.trip, false);
});

test('§4.2 LOWER bound — same run, all errors already in processed: still trips', () => {
    // This is the honest half of the bound: when every error is `not_eligible`,
    // the old denominator was already correct and this fix changes nothing.
    const r = shouldTripErrorRateBreaker(
        { errors: 40, processed: 263, errorsUnprocessed: 0 },
        CFG,
    );
    assert.equal((r.rate * 100).toFixed(1), '15.2');
    assert.equal(r.trip, true);
});

test('the sample gate stays on `processed`, so the fix adds NO new stop', () => {
    // attempts = 149 would clear a gate of 50; processed = 49 must keep it shut.
    const r = shouldTripErrorRateBreaker(
        { errors: 100, processed: 49, errorsUnprocessed: 100 },
        CFG,
    );
    assert.equal(r.trip, false);
    assert.match(r.reason, /sample gate/);
});

test('strict comparison preserved: exactly at the threshold does not trip', () => {
    // 15/100 = 15.0% exactly → not > 0.15 → no trip.
    const at = shouldTripErrorRateBreaker(
        { errors: 15, processed: 100, errorsUnprocessed: 0 },
        CFG,
    );
    assert.equal(at.trip, false);

    // 1504/10000 = 15.04% → trips, and DISPLAYS as "15.0%". This is the rounding
    // artefact behind the three runs logged at exactly 15,0% (spec §1).
    const justOver = shouldTripErrorRateBreaker(
        { errors: 1504, processed: 10000, errorsUnprocessed: 0 },
        CFG,
    );
    assert.equal(justOver.trip, true);
    assert.match(justOver.reason, /15\.0%/);
});

test('maxErrorRate = 0 disables the signal (routes.ts `> 0` semantics)', () => {
    const r = shouldTripErrorRateBreaker(
        { errors: 500, processed: 100, errorsUnprocessed: 500 },
        { minSample: 50, maxErrorRate: 0 },
    );
    assert.equal(r.trip, false);
});

test('zero denominator yields 0, not NaN', () => {
    const r = shouldTripErrorRateBreaker(
        { errors: 0, processed: 0, errorsUnprocessed: 0 },
        { minSample: 0, maxErrorRate: 0.15 },
    );
    assert.equal(r.rate, 0);
    assert.equal(r.trip, false);
});

test('the reason keeps the grepped prefix on trip', () => {
    const r = shouldTripErrorRateBreaker(
        { errors: 50, processed: 100, errorsUnprocessed: 0 },
        CFG,
    );
    assert.equal(r.trip, true);
    assert.ok(
        r.reason.startsWith('Error rate too high ('),
        `production logs are grepped on this prefix, got: ${r.reason}`,
    );
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd apps-microservices/crawler-service/crawler && npm test 2>&1 | tail -20`
Expected: FAIL — `Cannot find module './errorRateBreaker.js'`

- [ ] **Step 3: Write the implementation**

Create `apps-microservices/crawler-service/crawler/src/errorRateBreaker.ts`:

```ts
/**
 * Error-rate breaker decision (update mode, standard rates).
 *
 * Extracted from the inline block in routes.ts so it can be unit-tested at all:
 * this breaker was the only one of the three still computing its rate inline,
 * and it is the one that shipped a "rate" production observed at 722%.
 *
 * THE DEFECT THIS FIXES — the denominator excluded part of its own numerator.
 * `increment("processed")` happens at exactly one site, AFTER the HTTP status
 * policy. A dataset URL answering >= 400 or status 0 throws before that
 * increment, yet still increments `errors`. It counted in the numerator and
 * never in the denominator, so `errors / processed` was not a proportion —
 * 12 of the 69 runs stopped in the 2026-08-10 batch reported above 100%.
 *
 * ⚠ `errors` MIXES TWO NATURES, unlike the numerators of the two neighbouring
 * breakers (`shouldTripProxyWall`, `shouldTripExternalRedirectBreaker`), which
 * are disjoint from `processed` by construction:
 *   - CASE 1, HTTP error on a dataset URL   → never reaches `processed`  (OFF-BOOK)
 *   - CASE 3, 2xx same URL, no longer eligible → counted after it        (ON-BOOK)
 * `processed + errors` would therefore double-count the on-book half and dilute
 * the rate for the runs whose rate is already correct. The denominator is
 * `processed + errorsUnprocessed`, isolating the off-book half only.
 *
 * INVARIANT — the rate cannot exceed 1. Every on-book error is a URL already
 * inside `processed`, so `errors <= processed + errorsUnprocessed = attempts`.
 * A rate above 1 now means a counter bug, not a broken site.
 *
 * ⚠ THE SAMPLE GATE STAYS ON `processed`, NOT on `attempts`. Widening it would
 * let the breaker evaluate runs it never evaluated before (processed = 10 with
 * errorsUnprocessed = 45 opens a gate of 50 that 10 kept shut), i.e. it would
 * ADD stops. This change exists to remove stops decided on an invalid number.
 *
 * Pure function (no Crawlee/Redis) so it is unit-testable in isolation.
 */
export interface ErrorRateBreakerStats {
    /** Cumulative `errors` counter — BOTH natures. */
    errors: number;
    /** Cumulative `processed` — URLs that passed the HTTP status policy. */
    processed: number;
    /** Cumulative `errors_unprocessed` — the OFF-BOOK half of `errors` only. */
    errorsUnprocessed: number;
}

export interface ErrorRateBreakerConfig {
    minSample: number;
    maxErrorRate: number;
}

export function shouldTripErrorRateBreaker(
    stats: ErrorRateBreakerStats,
    cfg: ErrorRateBreakerConfig,
): { trip: boolean; rate: number; attempts: number; reason: string } {
    const attempts = stats.processed + stats.errorsUnprocessed;
    const rate = attempts > 0 ? stats.errors / attempts : 0;

    if (stats.processed < cfg.minSample) {
        return {
            trip: false,
            rate,
            attempts,
            reason: `below sample gate (processed ${stats.processed}/${cfg.minSample})`,
        };
    }
    if (!(cfg.maxErrorRate > 0)) {
        return { trip: false, rate, attempts, reason: "error-rate signal disabled (maxErrorRate = 0)" };
    }
    if (rate > cfg.maxErrorRate) {
        return {
            trip: true,
            rate,
            attempts,
            // Prefix is load-bearing: production logs are grepped on it.
            reason: `Error rate too high (${(rate * 100).toFixed(1)}% > ${cfg.maxErrorRate * 100}%, `
                + `${stats.errors} errors / ${attempts} attempts)`,
        };
    }
    return {
        trip: false,
        rate,
        attempts,
        reason: `error rate ${(rate * 100).toFixed(1)}% within threshold`,
    };
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd apps-microservices/crawler-service/crawler && npm test 2>&1 | tail -20`
Expected: `fail 0`, and `tests` = 435 + the number of tests you wrote (9 as written above)

- [ ] **Step 5: Prove the invariant test can actually fail**

A guard that cannot fail proves nothing. Temporarily change `attempts` in the implementation to `stats.processed` alone, re-run, and confirm the invariant test and the two bound tests go red. **Revert the mutation** before committing.

Run: `cd apps-microservices/crawler-service/crawler && npm test 2>&1 | tail -20`
Expected while mutated: `fail` ≥ 3. After revert: `fail 0`.

- [ ] **Step 6: Commit**

```bash
git add apps-microservices/crawler-service/crawler/src/errorRateBreaker.ts \
        apps-microservices/crawler-service/crawler/src/errorRateBreaker.test.ts
git commit -F - <<'MSG'
feat(crawler-service): the error-rate breaker becomes a pure, testable proportion

Extracts the inline rate from routes.ts into shouldTripErrorRateBreaker(),
the last of the three breakers still computing its rate in the handler and
the only one without a test. The denominator becomes processed +
errorsUnprocessed, which makes a rate above 1 structurally impossible; the
sample gate deliberately stays on `processed` so the change can only remove
stops, never add them. Tests encode both bounds of the spec: all-off-book
rescues the marginal run, all-on-book still trips.

Not wired yet — routes.ts still uses the inline computation.

FR — le disjoncteur du taux d erreurs devient une proportion pure et testable

Extrait le calcul en ligne de routes.ts vers shouldTripErrorRateBreaker(),
le dernier des trois disjoncteurs a calculer son taux dans le handler et le
seul sans test. Le denominateur devient processed + errorsUnprocessed, ce qui
rend un taux superieur a 1 structurellement impossible ; la porte
d echantillon reste sur `processed`, pour que le changement ne puisse que
retirer des arrets, jamais en ajouter. Les tests epinglent les deux bornes de
la spec : tout hors-livre recupere le run marginal, tout au-livre declenche
encore.

Pas encore cable : routes.ts utilise toujours le calcul en ligne.
MSG
```

---

## Task 3: The `errors_unprocessed` counter

**Goal:** A counter incremented exactly once per dataset URL whose error never reached `increment("processed")`, written where that fact is known, with the write/read name agreement pinned.

**Files:**
- Modify: `apps-microservices/crawler-service/crawler/src/class/UpdateChecker.ts` (CASE 1, at the `increment("errors")` on ~`:175`)
- Create: `apps-microservices/crawler-service/crawler/src/errorsUnprocessedParity.test.ts`

**Acceptance Criteria:**
- [ ] The increment sits in CASE 1's `isFromDataset` branch, immediately after `increment("errors")`
- [ ] It is added at **exactly one** site — `UpdateChecker.ts` CASE 3 must stay untouched
- [ ] `errors` itself is unchanged: same sites, same conditions, same count
- [ ] The counter goes through `StatsManager` (Redis), **not** a `context`-local field — `errors` and `processed` are cumulative across restarts, and mixing a process-local counter into their ratio would corrupt it after any restart
- [ ] A parity test pins the write side only — that `UpdateChecker.ts` increments the name `errors_unprocessed`
  - The read side (`routes.ts` calling `getValue("errors_unprocessed")`) is deliberately deferred to **Task 4's Step 3b**: `routes.ts` has no read of this counter until that task wires it, so an assertion on the read side here could not pass.
- [ ] `npm test` green

**Verify:** `cd apps-microservices/crawler-service/crawler && npm test` → `fail 0`; and `grep -c 'increment("errors_unprocessed")' src/class/UpdateChecker.ts` → `1`

**Steps:**

- [ ] **Step 1: Write the failing parity test**

Create `apps-microservices/crawler-service/crawler/src/errorsUnprocessedParity.test.ts`:

```ts
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

/**
 * `errors_unprocessed` is written in UpdateChecker.ts and read back in routes.ts
 * by NAME, through a Redis hash — nothing type-checks that the two literals
 * agree. A typo on either side leaves the breaker reading a permanently-absent
 * field, i.e. a denominator silently equal to `processed`: the exact defect this
 * lot exists to close, restored in a form that looks fixed. So it is pinned.
 *
 * Source-text assertions on purpose: routes.ts needs a live Crawlee handler and
 * UpdateChecker's CASE 1 needs a live StatsManager; a fake would only prove the
 * fake agrees with itself.
 */
const src = (f: string) => fs.readFileSync(path.join(import.meta.dirname, f), "utf-8");

test("errors_unprocessed: UpdateChecker writes the name routes.ts reads", () => {
    const checker = src("class/UpdateChecker.ts");

    assert.ok(
        checker.includes('increment("errors_unprocessed")'),
        'UpdateChecker.ts must increment "errors_unprocessed" — without it the denominator is `processed` again',
    );
    // Read-side assertion (routes.ts getValue("errors_unprocessed")) deferred to
    // Task 4 Step 3b — routes.ts has no read of this counter until that task wires it.
});

test("errors_unprocessed is written ONCE, on the HTTP-error branch only", () => {
    const checker = src("class/UpdateChecker.ts");

    const increments = checker.match(/increment\("errors_unprocessed"\)/g) ?? [];
    assert.equal(
        increments.length,
        1,
        "expected exactly one increment site — CASE 3 (2xx not_eligible) is already inside `processed`",
    );

    // It must sit in CASE 1 (isHttpError), i.e. before CASE 3's own errors++.
    const case3 = checker.indexOf("CASE 3: Success");
    const increment = checker.indexOf('increment("errors_unprocessed")');
    assert.ok(case3 !== -1, "the CASE 3 marker comment must still exist");
    assert.ok(
        increment < case3,
        "the increment must live in CASE 1 (HTTP error), which throws before increment(\"processed\")",
    );
});

test("`errors` keeps exactly its two live writers in UpdateChecker", () => {
    const checker = src("class/UpdateChecker.ts");
    const increments = checker.match(/increment\("errors"\)/g) ?? [];
    assert.equal(
        increments.length,
        2,
        "`errors` feeds the BO health guard and both deletion caps — this lot must not change its count",
    );
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd apps-microservices/crawler-service/crawler && npm test 2>&1 | tail -20`
Expected: FAIL — `UpdateChecker.ts must increment "errors_unprocessed"`

- [ ] **Step 3: Add the increment**

In `apps-microservices/crawler-service/crawler/src/class/UpdateChecker.ts`, CASE 1, find:

```ts
        if (isHttpError) {
            if (isFromDataset) {
                await this.statsManager.increment("errors");
```

and make it:

```ts
        if (isHttpError) {
            if (isFromDataset) {
                await this.statsManager.increment("errors");
                // Off-book half of `errors`: this URL threw on the HTTP status policy
                // (routes.ts) or exhausted its retries (failedRequestHandler), so it
                // never reached increment("processed"). The error-rate breaker needs it
                // in its denominator, or the ratio is not a proportion — see
                // errorRateBreaker.ts. CASE 3 below is NOT counted here: a 2xx
                // not_eligible URL is already inside `processed`.
                await this.statsManager.increment("errors_unprocessed");
```

Leave the existing comment block below it (the 404/410 deletion-claim rationale) untouched.

- [ ] **Step 4: Run to verify the parity test passes**

Run: `cd apps-microservices/crawler-service/crawler && npm test 2>&1 | tail -20`
Expected: `fail 0`, `tests` = previous total + 3

Note: the last assertion expects `increment("errors")` **twice** in `UpdateChecker.ts` (CASE 1 and CASE 3). If the runner reports a different number, do not edit the number to match — read the file and find out why it changed.

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/crawler-service/crawler/src/class/UpdateChecker.ts \
        apps-microservices/crawler-service/crawler/src/errorsUnprocessedParity.test.ts
git commit -F - <<'MSG'
feat(crawler-service): count the errors that never reach `processed`

`errors` mixes two natures and only one of them bypasses the `processed`
counter: an HTTP error throws before the increment, a 2xx not_eligible
verdict is already inside it. errors_unprocessed isolates the first, at the
single site that knows the difference, so the breaker's denominator can be
total attempts without double-counting the second. Goes through StatsManager,
not a context field: `errors` and `processed` are cumulative across restarts
and a process-local counter would corrupt the ratio after one. `errors`
itself is untouched — it feeds the BO health guard and both deletion caps.

FR — compter les erreurs qui n atteignent jamais `processed`

`errors` melange deux natures et une seule contourne le compteur
`processed` : une erreur HTTP leve avant l increment, un verdict 2xx
not_eligible y est deja compte. errors_unprocessed isole la premiere, au seul
endroit qui connait la difference, pour que le denominateur du disjoncteur
puisse etre le total des tentatives sans double-compter la seconde. Passe par
StatsManager et non par un champ de contexte : `errors` et `processed` sont
cumulatifs entre redemarrages, un compteur local au processus corromprait le
rapport apres l un d eux. `errors` lui-meme est intact — il alimente la garde
de sante du BO et les deux plafonds de suppression.
MSG
```

---

## Task 4: Wire it, and document the mechanism that was documented nowhere

**Goal:** `routes.ts` delegates the error-rate decision to the pure function, and the service's `CLAUDE.md` finally describes the breaker that stopped 69 runs of a batch.

**Files:**
- Modify: `apps-microservices/crawler-service/crawler/src/routes.ts` (import at ~`:33`, block `:449-467`)
- Modify: `apps-microservices/crawler-service/crawler/src/errorsUnprocessedParity.test.ts` (restore the read-side assertion — see Step 4b)
- Modify: `apps-microservices/crawler-service/CLAUDE.md` (new section after `## Update Mode …`, ~`:83`)

**Acceptance Criteria:**
- [ ] No arithmetic on the error rate is left inline in `routes.ts`
- [ ] `redirectRate` stays inline and unchanged — its branch is disabled in production (`maxRedirectRate` arrives as `0.0`) and the spec puts it out of scope
- [ ] The `if (processed >= cb.minSample)` wrapper is kept, so the redirect and growth branches keep their existing gate
- [ ] `cb` is passed straight to the pure function (structural typing: it already carries `minSample` and `maxErrorRate`)
- [ ] **The read-side parity assertion is restored** in `errorsUnprocessedParity.test.ts`, and the docblock sentence saying it is deferred is removed — this task is the "later" that sentence points at
- [ ] `CLAUDE.md` gains a section naming the breaker, its three thresholds, the two that arrive disabled, the exit-code consequence, and the dead micro mode
- [ ] `npm test` green
- [ ] All three files in **one** commit — the spec requires the doc section to ship with the fix

**Verify:** `cd apps-microservices/crawler-service/crawler && npm test` → `fail 0`; and `grep -c 'errors / processed' src/routes.ts` → `0`; and `grep -c 'getValue("errors_unprocessed")' src/errorsUnprocessedParity.test.ts` → `2`

⚠ **Why the parity test is in this task's file list.** Task 3 wrote the counter but could not pin that anyone *reads* it — `routes.ts` had no read until now, so the assertion was removed from Task 3 and deferred here. **This task is the only place it can pass, and the only place that will remember it.** Dropping it leaves the write/read name agreement unpinned, which is the precise defect the parity test exists to prevent: a counter incremented into one field while the breaker reads a permanently-absent other, i.e. a denominator silently equal to `processed` again — the bug this whole lot repairs, restored in a form that looks fixed.

**Steps:**

- [ ] **Step 1: Add the import**

In `apps-microservices/crawler-service/crawler/src/routes.ts`, next to the existing breaker imports (~`:33`):

```ts
import { shouldTripErrorRateBreaker } from "./errorRateBreaker.js";
```

- [ ] **Step 2: Read the new counter alongside the others**

Find the four `getValue` reads (~`:449-452`) and add a fifth:

```ts
                    const errors = await context.statsManager.getValue("errors");
                    const redirects = await context.statsManager.getValue("redirects");
                    const newUrls = await context.statsManager.getValue("new_urls");
                    const processed = await context.statsManager.getValue("processed");
                    const errorsUnprocessed = await context.statsManager.getValue("errors_unprocessed");
```

- [ ] **Step 3: Replace the inline error-rate computation**

Find the standard-mode block:

```ts
                        if (processed >= cb.minSample) {
                            const errorRate = errors / processed;
                            const redirectRate = redirects / processed;

                            if (cb.maxErrorRate > 0 && errorRate > cb.maxErrorRate) abortReason = `Error rate too high (${(errorRate*100).toFixed(1)}% > ${(cb.maxErrorRate*100)}%)`;
                            else if (cb.maxRedirectRate > 0 && redirectRate > cb.maxRedirectRate) abortReason = `Redirect rate too high (${(redirectRate*100).toFixed(1)}% > ${(cb.maxRedirectRate*100)}%)`;
```

and replace those four lines with:

```ts
                        if (processed >= cb.minSample) {
                            // The error rate lives in a pure, tested module because its
                            // denominator is not `processed`: an HTTP error never reaches
                            // that counter. See errorRateBreaker.ts — 12 of 69 stopped runs
                            // in the 2026-08-10 batch reported a rate above 100%.
                            const errorBreaker = shouldTripErrorRateBreaker(
                                { errors, processed, errorsUnprocessed },
                                cb,
                            );
                            // Left inline on purpose: this branch is disabled in production
                            // (the BO launcher sends max_redirect_rate = 0) and the spec puts
                            // it out of scope. Do not "harmonise" it with the line above.
                            const redirectRate = redirects / processed;

                            if (errorBreaker.trip) abortReason = errorBreaker.reason;
                            else if (cb.maxRedirectRate > 0 && redirectRate > cb.maxRedirectRate) abortReason = `Redirect rate too high (${(redirectRate*100).toFixed(1)}% > ${(cb.maxRedirectRate*100)}%)`;
```

Leave the growth check that follows exactly as it is, inside the same wrapper.

- [ ] **Step 3b: Restore the read-side parity assertion**

`routes.ts` now reads the counter, so the assertion Task 3 could not make becomes provable. In `apps-microservices/crawler-service/crawler/src/errorsUnprocessedParity.test.ts`, the first test currently pins only the write side. Re-add the read side to it:

```ts
    const routes = src("routes.ts");
    assert.ok(
        routes.includes('getValue("errors_unprocessed")'),
        'routes.ts must getValue("errors_unprocessed") — a name mismatch reads a field nobody writes, i.e. a denominator silently back to `processed`',
    );
```

Then remove the docblock sentence stating the read-side assertion is deferred until `routes.ts` reads the counter — it is no longer deferred, and a stale "later" in a test file is how a deferral becomes permanent.

- [ ] **Step 4: Run the suite**

Run: `cd apps-microservices/crawler-service/crawler && npm test 2>&1 | tail -20`
Expected: `fail 0`, same total as after Task 3

Then prove the restored assertion can fail: temporarily rename the read in `routes.ts` to `getValue("errors_unprocessed_typo")`, re-run, confirm that assertion goes red, and revert. Show both runs in your report — an assertion nobody has seen fail is not a guard.

- [ ] **Step 5: Add the missing `CLAUDE.md` section**

Confirm first that the gap is real (it was, on 2026-08-24: all four terms at 0 occurrences):

```bash
cd apps-microservices/crawler-service
for t in "circuit breaker" "maxErrorRate" "minSample" "circuitBreaker"; do printf '%-18s : %s\n' "$t" "$(grep -ci "$t" CLAUDE.md)"; done
```

Then insert this section immediately **after** the `## Update Mode (Archived Previous Crawl Handling)` block (i.e. before `## Regional Path Exclusion`):

```markdown
## Circuit Breaker (Update Mode Rate Guards)

`routes.ts` — "Circuit Breaker Check (Dual-Mode)". Armed only in update mode (`main.ts`). On fire
it sets `context.stopReason = "circuitBreaker"` and stops the crawler. **It sets no fatal exit
code**: the run exits 2, which the service classifies as **success**, and the stop webhook carries
`isError = "circuitBreaker"`. BO-side that becomes an `update_crawling_history` row in `FAILED`,
and `est_domaine_deja_en_cours()` tests `status IN ('PENDING','RUNNING','FAILED','STOPPED')` with
**no date bound** — so a trip locks its domain out of every future update. Do not treat this
breaker as a soft signal.

**Three thresholds, from `job.params`:**

| Param | Production value | Effect |
|---|---|---|
| `maxErrorRate` | `0.15` | the **only** live branch |
| `maxRedirectRate` | `0.0` | **disabled** — a `0` disables its branch (`> 0` guards) |
| `maxGrowthRate` | `0.0` | **disabled**, same reason |

Confirmed on production via `GET /admin/job/{crawl_id}` (2026-08-24), not from source alone.

**Sample gate:** `processed >= minSample` (50). Deliberately **not** widened to total attempts —
widening it would make the breaker evaluate runs it never evaluated, i.e. add stops.

**The error rate is not `errors / processed`.** `errors` mixes URLs that bypassed the `processed`
counter (HTTP error → throw) with URLs already inside it (2xx, no longer eligible). The rate is
computed in the pure `errorRateBreaker.ts` over `processed + errors_unprocessed`. Spec:
`docs/superpowers/specs/2026-08-24-circuit-breaker-error-rate-design.md`.

⚠ **`updateHealthVerdict.ts` still computes `errors / processed`** for the report the BO reads.
Same arithmetic, opposite stakes — deliberately out of scope, see §8.1 of that spec.

⚠ **Micro mode is dead code.** `cb.isMicroMode` is never set true (`main.ts`, the assignment is
commented out), so `maxAbsErrors` / `maxAbsRedirects` / `maxAbsNew` are inert here. Do not wake it
up as a side effect — reviving inert code changes behaviour, it does not repair it.
```

- [ ] **Step 6: Commit both files together**

```bash
git add apps-microservices/crawler-service/crawler/src/routes.ts \
        apps-microservices/crawler-service/CLAUDE.md
git commit -F - <<'MSG'
fix(crawler-service): the error-rate breaker stops deciding on a number above 100%

routes.ts now delegates to shouldTripErrorRateBreaker with total attempts as
the denominator. Direction stated plainly: a larger denominator means lower
rates and fewer stops. What makes that acceptable is not the direction but
the ground — a breaker deciding on 722% protects nothing, it draws lots. The
downstream guards are unchanged (health verdict, coverage gate, BO caps, and
since 2026-08-20 the active-orphan filter). redirectRate stays inline and
untouched: its branch arrives disabled from the BO launcher.

Ships with the CLAUDE.md section this mechanism never had: the file had zero
occurrences of "circuit breaker", maxErrorRate and minSample, for the guard
that stopped 69 runs of one batch and locked 121 eligible domains.

FR — le disjoncteur du taux d erreurs cesse de decider sur un nombre au-dela de 100 %

routes.ts delegue desormais a shouldTripErrorRateBreaker, avec le total des
tentatives au denominateur. Direction annoncee franchement : un denominateur
plus grand donne des taux plus bas, donc moins d arrets. Ce qui rend cela
acceptable n est pas la direction mais le fondement — un disjoncteur qui
decide sur 722 % ne protege rien, il tire au sort. Les gardes en aval sont
inchangees (verdict de sante, garde de couverture, plafonds du BO, et depuis
le 20/08 le filtre des orphelines actives). redirectRate reste en ligne et
intact : sa branche arrive desactivee du lanceur BO.

Livre avec la section CLAUDE.md que ce mecanisme n avait jamais eue : le
fichier comptait zero occurrence de « circuit breaker », maxErrorRate et
minSample, pour la garde qui a arrete 69 runs d un lot et verrouille 121
domaines eligibles.
MSG
```

---

## Out of scope — named so nobody adds it back

| Not done | Why |
|---|---|
| The `0.15` threshold | Spec §5. Deciding it needs the §4 composition measurement, which the user chose not to unblock. |
| A materiality floor (`errors >= maxAbsErrors`) | Spec §3: refuted by arithmetic. At `minSample = 50` a 15% rate needs 8 errors; the floor of 5 is already met. It would rescue **zero** of the 23 marginal runs. |
| `updateHealthVerdict.ts:69` | Same defect, opposite stakes — loosening it means **more** destructive actions applied. Spec §8.1. |
| Micro mode | Dead code (`isMicroMode` never true). Waking it changes behaviour. |
| `redirectRate` / `growthRate` | Both arrive as `0.0` from the BO launcher, i.e. disabled. |
| The 121 already-locked BO domains | A separate BO lot, and it must not ship before the flux is stemmed or we pay twice. |
| Stale `_callback_payload.json` replay | Second path to a `circuitBreaker` webhook without a trip. Unmeasured; discriminant is `details_json.date_start` vs the run's. |
| ⚠ `processed` double-counts retried URLs | One increment per handler entry that passed the status check, not per URL. Pre-existing, inflates the denominator (lenient direction). Noted, not fixed. |

**Deployment:** nothing to build here. This service runs on a remote VM absent from the workstation; delivery is the repo's CI/CD. There is no SFTP package, unlike this week's BO lots. Push and deploy are the user's calls.
