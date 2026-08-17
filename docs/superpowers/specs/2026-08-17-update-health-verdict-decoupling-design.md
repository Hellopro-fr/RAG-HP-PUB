# Update Health Verdict — Decoupling from the Circuit Breaker — Design

**Date:** 2026-08-17 (revision 2 — revision 1 was refuted by verification, see § What revision 1 got wrong)
**Service:** `crawler-service` (Node/TS crawler) **+ Marketplace BO** (two files)
**Scope:** two repos, two deployments, **hard ordering**. See § Deployment order.
**Status:** Approved (design)

## Problem

In **update mode**, every domain whose crawl processes fewer than 50 URLs receives the health
verdict `PENDING_SAMPLE` — permanently, by construction. The BO gate
(`script_process_update_crawling.php:636-639`) tests `health !== "HEALTHY"` with strict
inequality, so those domains can **never** have their detected deletions and redirections
applied. Not deferred: barred.

Measured 2026-08-17 on `update_crawling_history` (`FINISHED` runs): **134** runs under 50 crawled
URLs against **538** at 50 or above — **one update run in five**.

Over 10–17/08 this accounts for **20 of the 25** `Garde santé` alert mails. Attribution note:
`$appliquer_actions_destructives` has **four** writers — maintenance detected (`:631`), the health
gate (`:638`), the 50 %-of-corpus deletion cap (`:644`) and the 100-absolute cap (`:652`). The
attribution to the health gate is sound only because each mail carries
`$raison_blocage_destructif`, which names its own cause; those 20 name `health=PENDING_SAMPLE`.

## Root cause: one flag, two consumers

`circuitBreaker.isMicroMode` is **dead code**. Its two initialisations are `false`
(`context.ts:55`, `main.ts:160`), the single assignment to `true` is **commented out**
(`main.ts:983`), and the API cannot enable it — `app/schemas/crawler.py:43-57` exposes the rate
and absolute thresholds plus `min_sample`, but **no mode switch**.

Consequence: the `else` branch at `functions.ts:1438-1446` is **always** taken, so a run with
`processed < minSample` returns `PENDING_SAMPLE` at `:1444`.

The flag drives two unrelated decisions, in two different files:

| Consumer | Purpose | Effect of disabling micro mode |
|---|---|---|
| `routes.ts:456` | **aborts** an in-flight crawl (`abortReason`, absolute caps at `:458-460`) | intended — thresholds became explicit |
| `functions.ts:1434` | the `health` field of `_update_report.json`, **consumed by the BO** | unintended — `PENDING_SAMPLE` became permanent |

Disabling the flag for the first silently degraded the second.

### Why it was disabled — reconstructed 2026-08-17

`db1ec194` (2026-06-10 12:27) comments the line out. Its message is **subject-line only** — *"not
basing the circuit breaker using the number of URL in old dataset anymore"* — no body, so the
reasoning was never recorded, and the author no longer recalls it. Introduced 2026-03-11 by
`e3022005`; the commented state was preserved by the tree rollback `9fbd3407` (2026-07-17).

The previous day supplies the intent: the author was replacing an implicit heuristic with
**explicit configuration**.

- `7a79ddbc` (09/06 14:28) guards every *status-assigning* threshold with `threshold > 0 &&` in
  both `functions.ts` and `routes.ts` — **a threshold of zero means disabled.**
- `f0f7ec52` → `064ea5b8` → `98700b23` (09/06 17:53–18:01) add a **dedicated external-redirect
  breaker** with its own sample gate of **10**, explicitly independent of `minSample`
  (`2026-06-09-external-redirect-breaker-design.md:122`).

So the implicit switch on URL count had become obsolete **for the abort path**, the only subject
of that spec.

**This design does not reverse that decision.** The circuit breaker keeps its configuration
untouched.

> ⚠ **Do not uncomment `main.ts:983`.** Verified: `routes.ts:456` reads the flag and its MICRO
> branch aborts on absolute caps. Uncommenting would re-arm exactly what June removed.

## The live baseline — thresholds are overridden per run

**This is the fact that reshaped the design, and revision 1 missed it.** The BO does not use the
crawler's defaults. `tools/crawler/shell.php:134-147` builds an `update_thresholds` payload on
every update launch:

```php
"max_error_rate"    => $seuils_cb_payload['max_error_rate'],  // 0.15, from referentiel_seuils_cb
"max_redirect_rate" => 0,   // DISABLED
"max_growth_rate"   => 0,   // DISABLED
```

`app/schemas/crawler.py:51-53` accepts all three, so **the disables take effect**. In production
the health verdict is therefore a **single-signal instrument**: error rate at 15 %, gated by
sample size. Redirect rate and growth rate are inert. `min_sample` and the three `max_abs_*` are
**not** sent, so they keep their `context.ts` defaults (50, and 5/10/20).

Two consequences:

1. **Graduating redirects and growth would switch on two checks production deliberately turned
   off.** This design does not do that.
2. Setting a rate to zero is a *deliberate operator gesture*, not an accident — `shell.php:141-145`
   uses it for force-resume ("ignorer le seuil d'erreurs du circuit breaker pour cette relance").
   Any threshold arithmetic must preserve it.

A rate referential already exists: `referentiel_seuils_cb`, read by
`get_seuils_cb_pour_payload_crawler()` (`fonctions_crawl_metrics.php:430-467`) with a hardcoded
fallback of 15/30/50 %. A review tool exists too, `script_revue_seuils_cb.php`. Any new tunable
belongs there, not hardcoded in `context.ts`.

## Options rejected

**Have the BO send a low `min_sample`.** Correction to revision 1: it claimed the BO "sends
nothing today". **That was false** — the BO already builds `update_thresholds`, so this option is
*one extra key* in an existing payload, not a new integration. It is still rejected, but on the
instrument argument alone: with redirect and growth disabled, the only live check is the error
*rate*, and a rate over 12 pages is noise — 2 errors on a 12-URL site is 16.7 %, above the 15 %
threshold. Lowering `min_sample` would replace a systematic block with an arbitrary one.

**Restore micro mode as-is.** Would re-arm the abort path (`routes.ts:456`) and would activate the
two disabled signals via their absolute caps. Rejected.

**Keep two modes, recalibrate.** Retains the cliff at 50 URLs and requires defending hand-picked
numbers against a referential that already owns them.

## Design

The verdict answers one question: **was this crawl representative of the previously known
population?** It is *not* a deletion-safety net — the BO already has one, applied after the
HEALTHY test: `UPDATE_DELETED_CAP_ABS = 100` and `UPDATE_DELETED_CAP_PCT = 0.5` (`:644`, `:651`).

### Governing constraint: no run that passes today may newly fail

Every change below is a **strict relaxation**. Any run that reaches `HEALTHY` under the current
code must still reach `HEALTHY`. This is what makes the service deployable ahead of the BO review,
and it is the acceptance criterion for the whole change.

### A pure decision module

Mirrors `externalRedirectBreaker.ts` (same author, same subject area, June): a dependency-free
decision helper with unit tests.

```
crawler/src/updateHealthVerdict.ts        NEW  — pure
crawler/src/updateHealthVerdict.test.ts   NEW  — node:test
crawler/src/functions.ts:1430-1462        replaced by a call
crawler/src/class/UpdateChecker.ts        one new counter increment per dataset outcome
```

`npm test` is `node --import tsx --test src/**/*.test.ts` and runs locally — unlike the BO, this
repo has a working runner.

`generateUpdateReport` (`functions.ts:1414`) keeps the `ABORTED` override, which depends on
`context.stopReason` — context state, not a metric. Everything numeric moves into the module,
including the mass-deletion `SUSPECT` guard (`:1453-1457`).

### Representativeness: a disjunction, not a replacement

`minSample = 50` measures the wrong thing — a 12-page site that crawled all 12 pages is fully
representative and is declared an insufficient sample. But replacing it outright would newly
block large partial crawls that pass today (60 processed against a 500-URL corpus passes
`60 >= 50` and would fail a coverage test). That violates the governing constraint.

So the gate becomes a **disjunction**:

```
PENDING_SAMPLE  ⟺  processed < minSample  AND  coverage < minCoverage
```

A run is representative if it has **either** an absolute sample **or** good coverage. Provably
non-regressive: every run passing today (`processed >= minSample`) still passes, and small
complete crawls now pass too.

### A sound coverage numerator

Revision 1 proposed `(processed + errors) / previousTotal`. **Verification refuted it** on three
counts:

- `processed` is incremented with **no source filter** (`routes.ts:441-444`), so it counts newly
  discovered URLs, while `previousTotal` is dataset-scoped — mismatched populations.
- A dataset URL that is HTTP-200 but fails eligibility increments `processed` (`routes.ts:444`)
  **and then** `errors` (`UpdateChecker.ts:274`, CASE 3) in the same handler pass — double count.
- A followed redirect increments `processed` **and** `redirects` — double count again.

The comment at `functions.ts:1449-1452` asserting that errors do not count toward `processed` is
itself **only true for CASE 1** (permanent HTTP status throws at `routes.ts:436` before `:444`).
It names "CASE 1/3"; CASE 3 contradicts it. Fix that comment in the same change.

The sound numerator is a **dedicated, dataset-scoped counter**, incremented exactly once per
previously-known URL that reached a terminal decision:

```
accounted  — incremented once in each isFromDataset terminal branch of UpdateChecker.checkUrl
             (confirmed alive | deleted | unverified | redirected off-dataset | redirect to a
             confirmed dataset URL)
coverage = accounted / previousTotal
```

This mirrors how `errors` is already correctly scoped in that class. It must **not** reuse
`processed`.

⚠ `previousTotal = consolidationCounts.dataset` (`main.ts:979`) is the previous **Dataset**
population — a strict subset of the previously-known corpus, which also includes
request-queue- and request-url-sourced URLs (`UrlConsolidator.ts:248`). The numerator is scoped to
the same subset, so the ratio is internally consistent; the spec calls it *"the previous Dataset
population"*, never *"the corpus"*.

### Thresholds: a materiality conjunct, not a graduated maximum

The error signal fires only when the rate is bad **and** the absolute count is material:

```
CRITICAL  ⟺  maxErrorRate > 0  AND  errorRate > maxErrorRate  AND  errors >= maxAbsErrors
```

with `errorRate = errors / processed`, exactly as today.

Revision 2 first proposed `max(maxAbsErrors, maxErrorRate × previousTotal)`. **That was wrong and
violated this design's own non-regression constraint**, because it silently changes the
denominator from `processed` to `previousTotal`. Counter-example: `previousTotal = 100`,
`processed = 200`, `errors = 20` — today `20/200 = 10 %`, below 15 %, so `HEALTHY`; under the
maximum, `20 >= 15`, so `CRITICAL`. A site that grew would be newly blocked.

The conjunction has four properties the maximum lacked:

- **Strictly non-regressive** — it only adds a conjunct, so it can never produce a `CRITICAL` the
  current code does not.
- **Fixes the small-sample noise** the whole design is about: 2 errors on a 12-URL site is 16.7 %
  and would fire on rate alone, but `2 < 5` so it does not fire.
- **No denominator change** — `errorRate` keeps its current definition, so `previousTotal` plays no
  part in this test and none of its scoping problems apply.
- **Both operators are preserved verbatim** from the existing code: `>` on the rate
  (`:1440`), `>=` on the absolute count (`:1435`). Nothing to arbitrate, nothing to transcribe
  wrongly.

The leading `maxErrorRate > 0` conjunct is the existing disable guard from `7a79ddbc`, kept in
place. A rate of zero means the operator switched the check off (`shell.php:141-145`, force-resume)
and the absolute floor must **not** resurrect it — expressing the rule as a conjunction makes that
automatic, where a `max()` would have inverted it.

**Redirects and growth are left exactly as production has them: disabled.** Applying floors to them
would activate dormant checks. If an operator re-enables a rate through `referentiel_seuils_cb`,
the same conjunction extends to it — as a separate, measured decision.

Severity mapping is unchanged and identical in both existing branches — errors → `CRITICAL`,
redirects → `CRITICAL`, new URLs → `WARNING`. No new severity is introduced.

`minSample` **stays** in `context.ts` and in the report: `routes.ts:463` uses it for the abort
path. Only the verdict stops treating it as a sole gate.

### Evaluation order

**Phase 1 — base verdict** (first match wins):

```
1. previousTotal > 0 AND processed < minSample AND accounted/previousTotal < minCoverage
                                       → PENDING_SAMPLE
2. maxErrorRate > 0 AND errorRate > maxErrorRate AND errors >= maxAbsErrors
                                       → CRITICAL
3. maxRedirectRate > 0 AND redirectRate > maxRedirectRate AND redirects >= maxAbsRedirects
                                       → CRITICAL     (inert in production: rate is 0)
4. maxGrowthRate > 0 AND growthRate > maxGrowthRate AND newUrls >= maxAbsNew
                                       → WARNING      (inert in production: rate is 0)
5. otherwise                           → HEALTHY
```

`previousTotal <= 0` is a **guard on step 1**, not a branch of its own: with no denominator there
is no coverage objection, and steps 2-4 are unaffected — none of them divides by `previousTotal`
except `growthRate`, which is already guarded (`:1428`) and inert here anyway. (Revision 1 listed
it as a numbered step in an early-return chain, which transcribes into a return with no status.)

**Phase 2 — mass-deletion override** (unchanged logic, moved into the module):

```
previousTotal > 0 AND errors / previousTotal > 0.5 AND base ∈ { HEALTHY, PENDING_SAMPLE }
                                       → SUSPECT
```

`WARNING` and `CRITICAL` are deliberately **not** overridden — they already block, and replacing
their message would lose the more specific reason. This matches `:1454` exactly; do not widen it.

### Report shape

`functions.ts:1464-1491`. The BO reads `health`, `message`, `metrics.*` and `rates.*` — never
`mode` nor `thresholds` (enumerated: `:618`, `:619`, `:625`, `:636`, `:639`, `:641`, `:706-707`).
Note `rates.redirect_rate` **is** consumed, at `:625`, feeding
`detecter_et_marquer_maintenance()` — so `rates` must keep its current keys and meaning.

- `mode` — value becomes `"GRADUATED"`. Key retained.
- `metrics.accounted`, `rates.coverage`, `thresholds.min_coverage`, `thresholds.max_abs_new` —
  **new**, all additive. `max_abs_new` was missing while its two siblings were published.
- `thresholds.disabled_signals` — **new**, the list of signals skipped because their rate was
  `<= 0`. Without it a HEALTHY verdict is indistinguishable from a verdict whose checks were off.
- Everything the BO reads — **unchanged**.

Naming: the TS config key is `minCoverage`, the JSON field `min_coverage`, mirroring
`minSample`/`min_sample`. Both spellings are intentional; do not unify them.

## BO changes

Two, not one — revision 1 understated this:

1. `script_process_update_crawling.php:637` stops blocking on `WARNING`. Growth does not qualify
   the safety of a deletion, and the BO's own caps remain in force. (Inert until a growth rate is
   re-enabled, but correct.)
2. **The reconciliation coverage gate must move to the same numerator.** It currently requires
   `processed >= 0.8 × previous_total` (`:698-707`). On exactly the population this design
   unblocks — a genuine mass deletion, where `processed` is low because the pages are gone —
   `processed`-only coverage still fails, so reconciliation stays skipped. It must consume
   `metrics.accounted` instead.

## Deployment order

**Service first, BO second** — the service produces the verdict the BO interprets, and the BO
changes are additive.

Correction to revision 1, which called service-first *"strictly safe"*. **It is not.** The service
deployment is where the behaviour change lands: the moment it ships, small-corpus runs stop
returning `PENDING_SAMPLE`, and the *unchanged* BO gate begins applying their deletions and
redirections. That is the intended outcome, and it is bounded by the BO's existing caps (100
absolute / 50 % of corpus) — but it is a live behaviour change on ~20 % of update runs, so the
service package is the one that needs review, not the BO one.

## Testing

`updateHealthVerdict.test.ts` pins, at minimum:

- small site, full accounting coverage → `HEALTHY` (the defect being fixed);
- `processed >= minSample` with poor coverage → **still** `HEALTHY` (the non-regression
  constraint; this is the case a replacement gate would have broken);
- coverage 17 % with 0 errors and `processed < minSample` → `PENDING_SAMPLE` (collapsed crawl);
- the same coverage with high errors → judged on the error threshold, not `PENDING_SAMPLE`;
- error rate `<= 0` (operator force-resume) with errors above the floor **and** a bad ratio →
  **check skipped**, not `CRITICAL` — the disable-wins rule;
- rate above threshold but `errors < maxAbsErrors` → `HEALTHY` (the materiality conjunct; this is
  the small-sample noise case, e.g. 2 errors on 12 URLs);
- exactly `maxAbsErrors` errors **with** the rate above threshold → `CRITICAL` (pins `>=` on the
  count and `>` on the rate);
- a grown site — `previousTotal` well below `processed`, rate below threshold, errors above the
  floor → `HEALTHY` (pins the non-regression counter-example that killed the `max()` form);
- `previousTotal = 0` → no coverage verdict, and the error test still evaluated normally on
  `processed` (pins that the guard skips coverage only, not the whole verdict);
- redirects and growth at their production values (rate 0) → never `CRITICAL`/`WARNING`;
- the `SUSPECT` guard overriding `HEALTHY` and `PENDING_SAMPLE`, and **not** overriding `WARNING`
  or `CRITICAL`;
- a **positive control**: a metric set that must produce a non-HEALTHY verdict, so a module
  returning `HEALTHY` unconditionally cannot pass for the wrong reason.

## Calibration limits — what this design does NOT rest on

Stated plainly, because revision 1 overstated its evidence.

1. **The formula was never replayed against history.** `previous_total` is not persisted by the BO
   (`script_revue_seuils_cb.php:149`). Reconstructing it by self-joining `id_previous_crawl`
   failed: **74 of 80** measurable runs have no usable previous count. Only 2 resolved — 884
   (41/243, 0 errors) and 717 (37/187), both collapsed crawls, both agreeing with the design.
2. **The `1448 ≈ 100 % coverage` row of revision 1 had no denominator** and has been removed from
   the argument. It is a high-error run (16 errors on 45 crawled); its coverage is unknown.
3. **The blast radius of the coverage gate on the 538 large runs is unmeasurable** for the same
   reason. This is why the gate is a disjunction rather than a replacement: the unmeasurable case
   cannot bite, because those runs already pass on `processed >= minSample`.
4. **The live threshold values were not read from the running service.** They are inferred from
   `shell.php` plus `context.ts` defaults. `referentiel_seuils_cb` is not readable through the
   available tooling (table not whitelisted), so the 15 % figure is the fallback constant, not a
   confirmed live value.
5. What *was* measured, on 80 runs (the 54 unmeasurable ones all predate 2026-05-12, so this is
   the whole current-regime population, not a convenience slice): under absolute caps, **64 of 80
   (80 %)** would return HEALTHY. On the live slice since 01/08 (n=20): **13 HEALTHY, 6 WARNING,
   1 CRITICAL** — and since production disables the growth signal, those **6 WARNING become
   HEALTHY**, giving **19 of 20** unblocked.

## What revision 1 got wrong

Kept deliberately: this list is the reason the design changed, and it is cheaper to read than to
rediscover.

| Claim | Verdict |
|---|---|
| `(processed + errors)` is a sound numerator | **REFUTED** — unscoped, and double-counts twice over |
| `processed` and `errors` are disjoint | **REFUTED** — CASE 3 increments both |
| `previousTotal` is the previously-known corpus | subset only (Dataset), not the corpus |
| "the BO sends no thresholds today" | **FALSE** — `shell.php:134-147` sends three |
| "service-first is strictly safe" | false — that is where the behaviour change lands |
| the BO change is one line | two changes; the reconciliation gate must move too |
| every threshold comparison carries `> 0 &&` | status-assigning ones do; `processed >= minSample` does not |
| a threshold of 0 makes everything CRITICAL | inverted — the danger is `max()` **resurrecting** a disabled check |

And one thing revision 2 got wrong before it was committed, caught by re-reading its own
non-regression constraint: graduating the error threshold as
`max(maxAbsErrors, maxErrorRate × previousTotal)` silently swaps the denominator from `processed`
to `previousTotal`, which newly blocks any site that grew. Replaced by a conjunction, which adds a
materiality condition instead of competing with the rate. See § Thresholds.

## Follow-ups (out of scope)

1. **Persist `previous_total` and `accounted` in the BO** so the next calibration is possible; and
   register `min_coverage` in `referentiel_seuils_cb` rather than hardcoding it.
2. `crawler-service/CLAUDE.md` documents neither the dual-mode breaker nor the health vocabulary,
   though the BO depends on it. Add the verdict table beside the exit-code table.
3. Read the live thresholds from the running service and compare against `context.ts` — limit 4
   above.
4. `id_previous_crawl` resolves for a small minority of BO rows, and some previous rows carry
   `urls_crawled = 0`. Noticed while measuring; not investigated.
