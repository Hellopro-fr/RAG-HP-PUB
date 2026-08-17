# Update Health Verdict — Decoupling from the Circuit Breaker — Design

**Date:** 2026-08-17
**Service:** `crawler-service` (Node/TS crawler) **+ Marketplace BO** (`script_process_update_crawling.php`)
**Scope:** two repos, two deployments, **hard ordering** (service first). See § Deployment order.
**Status:** Approved (design)

## Problem

In **update mode**, every domain whose previous corpus is under 50 URLs receives the health
verdict `PENDING_SAMPLE` — permanently, by construction. The Marketplace BO gate
(`script_process_update_crawling.php:637`) tests `health !== "HEALTHY"` with strict inequality, so
those domains can **never** have their detected deletions and redirections applied. Not deferred:
barred.

Measured 2026-08-17 on `update_crawling_history` (`FINISHED` runs): **134** runs under 50 crawled
URLs against **538** at 50 or above — **one update run in five** is in the barred population. Over
the week of 10–17/08 this produced **20 of the 25** `Garde santé` alert mails.

## Root cause: one flag, two consumers

`circuitBreaker.isMicroMode` is **dead code**. Both initialisations are `false`
(`context.ts:55`), the single assignment to `true` is **commented out** (`main.ts:983`), and no API
parameter can enable it — `app/schemas/crawler.py:43-57` exposes `min_sample` and the three
`max_abs_*` but never the mode. Verified on two independent search forms.

Consequence: the `else` branch at `functions.ts:1438-1446` is **always** taken, so any run with
`processed < minSample` (default 50, `context.ts:59`) returns `PENDING_SAMPLE` at `:1444`. The
three `max_abs_*` API parameters are settable and **never read**.

The flag drives two unrelated decisions:

| Consumer | Purpose | Effect of disabling micro mode |
|---|---|---|
| `routes.ts` circuit breaker | **aborts** an in-flight crawl | intended — thresholds became explicit |
| `functions.ts:1434` health verdict | writes `health` to `_update_report.json`, **consumed by the BO** | unintended — `PENDING_SAMPLE` became permanent |

Disabling the flag for the first consumer silently degraded the second. The coupling is invisible
from either site because the consumers live in different files.

### Why it was disabled — reconstructed 2026-08-17

`db1ec194` (2026-06-10 12:27) comments the line out. Its message is **subject-line only** — *"not
basing the circuit breaker using the number of URL in old dataset anymore"* — no body, so the
reasoning was never recorded, and the author no longer recalls it. Introduced 2026-03-11 by
`e3022005`; the commented state was preserved by the tree rollback `9fbd3407` (2026-07-17).

The previous day supplies the intent, unambiguously: the author was replacing an implicit
heuristic with **explicit configuration**.

- `7a79ddbc` (09/06 14:28) guards every threshold with `threshold > 0 &&` in both `functions.ts`
  and `routes.ts` — **a threshold of zero means disabled**, i.e. a per-threshold switch driven
  from outside.
- `f0f7ec52` → `064ea5b8` → `98700b23` (09/06 17:53–18:01) add a **dedicated external-redirect
  breaker** with its own sample gate of **10**. Its spec
  (`2026-06-09-external-redirect-breaker-design.md:122`) states: *"Its own small sample gate (10)
  — not the breaker's `minSample=50` — so it fires in both micro and [non-micro]"*.

So the implicit switch on URL count had become **obsolete for the abort path**: thresholds were
explicit, and the small-corpus case had a dedicated breaker. A sound decision — but its scope was
the abort path, the only subject of that spec.

**This design does not reverse that decision.** The circuit breaker keeps its explicit,
corpus-size-independent configuration. Only the health verdict changes.

> ⚠ **Do not uncomment `main.ts:983`.** `isMicroMode` also feeds `routes.ts`, so re-enabling it
> would re-arm abort-on-absolute-caps — exactly what June removed. The fix is a **separate**
> decision for the verdict.

## Options rejected

**Have the BO send a low `min_sample`.** Mechanically works (`functions.ts:1439` reads
`cb.minSample`, and the BO sends nothing today — no `update_thresholds` or `min_sample` in
`fonctions_maj_crawling.php` or `fonctions_scrapping.php`). Rejected because the two branches use
different **instruments** by design: STANDARD judges by rate, MICRO by absolute count. Absolute
caps exist precisely *because a rate over 12 pages is meaningless*. On a 12-URL site, 2 errors is
16.7 % — above the 15 % threshold. Lowering `min_sample` replaces a systematic block with a
**noisy** verdict. Less code, wrong instrument.

**Restore micro mode as-is.** Would unblock most of the population (measured: 64 of 80 measurable
runs would return HEALTHY, 80 %) but imports a smaller defect — see § Graduation below.

**Keep two modes, recalibrate the constants.** Retains the cliff at 50 URLs and requires
defending every hand-picked number. No measurement supports new numbers (see § Calibration
limits).

## Design

The verdict answers exactly one question: **was this crawl representative of the known corpus?**
It is *not* a deletion-safety net — the BO already has one, applied after the HEALTHY test
(`:641-642`): `UPDATE_DELETED_CAP_ABS = 100` and `UPDATE_DELETED_CAP_PCT = 0.5`. Reconciliation
has its own separate coverage gate (`:698-703`). Separating these concerns is the core of this
design.

### A pure decision module

Mirrors the precedent set by `externalRedirectBreaker.ts` (same author, same subject area, June):
a dependency-free decision helper with unit tests.

```
crawler/src/updateHealthVerdict.ts        NEW  — pure, ~60 lines
crawler/src/updateHealthVerdict.test.ts   NEW  — node:test
crawler/src/functions.ts:1430-1462        replaced by a call
```

```ts
export interface UpdateHealthStats {
    processed: number; errors: number; redirects: number; newUrls: number; previousTotal: number;
}
export function decideUpdateHealth(
    stats: UpdateHealthStats,
    cfg: UpdateHealthConfig,
): { status: string; statusMessage: string }
```

No Crawlee, no Redis, no filesystem — `npm test` (`node --import tsx --test src/**/*.test.ts`)
covers it locally. This repo, unlike the BO, has a working test runner.

`generateUpdateReport` (`functions.ts:1412`) keeps the `ABORTED` override, which depends on
`context.stopReason` — context state, not a metric. Everything numeric moves into the module,
including the mass-deletion `SUSPECT` guard (`:1453`).

### Representativeness is coverage, not a count

`minSample = 50` measures the wrong thing. A 12-page site that crawled all 12 of its pages is
**100 % representative** and is declared an insufficient sample. A 500-page site that crawled 3
pages is not representative at all, and would pass any absolute floor.

The BO already models this correctly: `UPDATE_RECONCILIATION_COVERAGE_MIN = 0.8` is a **relative**
coverage gate.

### The trap: legitimate mass deletion looks like a collapsed crawl

Coverage alone cannot separate them. Domain 884 returned 41 URLs against a previous corpus of 243
— a site that deleted 200 pages, or a crawl that fell over?

The data answers, and the code already names the reason (`functions.ts:1449-1452`): **errors do
not count toward `processed`**, and `errors` ≈ deletion candidates.

| Signature | 884 | 1448 |
|---|---|---|
| Raw fetch coverage | 17 % (41/243) | ≈ 100 % |
| Errors | **0** | **16** |
| Reading | URLs **never attempted** → crawl collapsed | 404s **confirmed** → pages genuinely gone |

Hence the denominator correction: measure **accounting coverage**, not fetch coverage.

```
accounted = processed + errors
coverage  = accounted / previousTotal
```

*"What share of the known corpus did I account for, whether it answered or returned 404?"* A
collapsed crawl leaves the corpus unexplained; a genuine mass deletion explains all of it and is
then judged on the error threshold.

### Graduated thresholds — no new constants

```
threshold = max(absolute_floor, rate × previousTotal)
```

Below ~50 URLs the floor dominates; above it, the rate dominates. No cliff, no mode, no dead
branch.

| Signal | Floor (`context.ts:65-67`) | Rate (`context.ts:60-62`) | Verdict |
|---|---|---|---|
| `errors` | 5 | 0.15 | CRITICAL |
| `redirects` | 10 | 0.30 | CRITICAL |
| `newUrls` | 20 | 0.50 | WARNING |

**No number is invented.** Both sets are already in production; this design combines them with
`max()` instead of opposing them through a switch. The only new value is minimum coverage,
proposed at **0.8, borrowed from the BO's `UPDATE_RECONCILIATION_COVERAGE_MIN`**.

Why the ungraduated caps were a defect: the same 20-URL cap applied to a 10-URL site and a 47-URL
site. At 10 URLs, 20 new pages is 200 % growth — a legitimate alarm. At 47 URLs it is **43 %**,
*below* the standard 50 % threshold. At the top of the micro range the absolute cap was **stricter
than what a normal site faces**. Measured: all 6 `WARNING` runs in the live slice sit at 28–47
URLs.

### Evaluation order

Two phases, not one chain — the mass-deletion guard is an **override applied after** a base
verdict exists, which is how the current code is shaped (`:1453` runs after the if/else and tests
`status === "HEALTHY" || status === "PENDING_SAMPLE"`).

**Phase 1 — base verdict** (first match wins, early return):

```
1. previousTotal <= 0           → skip coverage entirely (no denominator; floors still apply)
2. coverage < minCoverage       → PENDING_SAMPLE  "crawl did not account for the known corpus"
3. errors    >= threshold_err   → CRITICAL
4. redirects >= threshold_redir → CRITICAL
5. newUrls   >= threshold_new   → WARNING
6. otherwise                    → HEALTHY
```

**Phase 2 — mass-deletion override** (unchanged logic, moved into the module):

```
previousTotal > 0
  AND errors / previousTotal > 0.5
  AND base verdict IS one of { HEALTHY, PENDING_SAMPLE }   → SUSPECT
```

`WARNING` and `CRITICAL` are deliberately **not** overridden: they already block, and replacing
their message with the SUSPECT one would lose the more specific reason. This matches `:1454`
exactly — do not widen it.

> ⚠ **Preserve the zero-means-disabled semantics from `7a79ddbc`.** If a computed threshold is
> `<= 0` (both floor and rate set to zero), the check must be **skipped**, not evaluated —
> `errors >= 0` is always true and would turn every run into `CRITICAL`. A disable switch that
> becomes a total block is the worst available failure mode; the module must test the threshold
> before applying it.

### Report shape

`_update_report.json` (`functions.ts:1464-1491`). The BO reads only `health`, `message` and
`metrics.*` (verified: `:618`, `:636`, `:639`, `:641`, `:706-707`) — it never reads `mode` or
`thresholds`, so those are free to change. Changes are otherwise **additive**:

- `mode` — value becomes `"GRADUATED"`. Key retained; verify no other consumer parses it.
- `metrics.accounted` — **new**, `processed + errors`.
- `rates.coverage` — **new**, the accounting coverage.
- `thresholds.min_coverage`, `thresholds.max_abs_new` — **new**. Note the two spellings are both
  intentional and mirror the existing split: the TS config key is `minCoverage` (like `minSample`),
  the JSON report field is `min_coverage` (like `min_sample`). Not a typo — do not unify them.
  `max_abs_new` was missing from a
  report that already published its two siblings; it becomes a live floor, so it must appear.
- `thresholds.effective.{errors,redirects,new_urls}` — **new**, the resolved `max()` values, so a
  verdict can be audited from the report alone.
- `health`, `message`, `metrics.{processed,errors,redirects,new_urls,previous_total}`, `rates.*`
  — **unchanged.**

### `previousTotal` availability

`main.ts:979` sets `previousTotal = consolidationCounts.dataset`, and `:972-975` **aborts with
exit code 4** when the previous corpus yields no URLs at all. So a run reaching the verdict
normally has a usable denominator; `previousTotal = 0` is a narrow edge (previous dataset empty
while the request queue is not), already guarded by the existing `> 0` tests. Step 1 above keeps
that behaviour explicit.

## BO change

One line: `script_process_update_crawling.php:637` stops blocking on `WARNING`. `CRITICAL`,
`SUSPECT`, `PENDING_SAMPLE` and `ABORTED` keep blocking.

Rationale: `WARNING` means "the site grew". Growth does not qualify the safety of a **deletion**,
and the BO's own caps (100 absolute / 50 %) remain in force behind the gate. Today a growth
warning bars deletions it does not describe.

## Deployment order

**Service first, BO second.** The service produces the verdict the BO interprets. Deploying the BO
first would stop blocking on a `WARNING` that the old service still emits with ungraduated
semantics — harmless but pointless. Deploying the service first is strictly safe: the new verdict
is never *more* permissive than the gate then in force.

## Testing

`updateHealthVerdict.test.ts` pins, at minimum:

- a small site with full accounting coverage → `HEALTHY` (the defect being fixed);
- domain 884's shape — coverage 17 %, 0 errors → `PENDING_SAMPLE` (collapsed crawl);
- the same coverage with high errors → judged on the error threshold, **not** `PENDING_SAMPLE`
  (genuine mass deletion);
- 20 new URLs against `previousTotal = 47` → `HEALTHY` (the ungraduated-cap defect);
- 20 new URLs against `previousTotal = 28` → `WARNING` (71 % growth is a real alarm);
- both floor and rate at zero → check **skipped**, not `CRITICAL` (the trap above);
- `previousTotal = 0` → no coverage verdict, floors still applied;
- the `SUSPECT` guard still overriding `HEALTHY` and `PENDING_SAMPLE`;
- a **positive control**: a metric set that must produce a non-HEALTHY verdict, so a module
  returning `HEALTHY` unconditionally cannot pass the suite for the wrong reason.

## Calibration limits — what this design does NOT rest on

The graduated formula **could not be replayed against history**, and this must not be presented
otherwise. `previous_total` is **not persisted** by the BO (`script_revue_seuils_cb.php:149` states
it). Reconstructing it by self-joining `id_previous_crawl` failed: **74 of the 80** measurable runs
have no usable previous count (unresolved join, or a previous row carrying
`urls_crawled = 0`). Only 2 resolved — 884 (41/243) and 717 (37/187), both genuine collapsed
crawls, both agreeing with the design.

So the formula rests on constants **already in production** plus those 2 verified cases, not on a
calibration. That is weaker evidence than a replay and is the main residual risk of this design.

What *was* measured, on 80 runs (the 54 unmeasurable ones all predate 2026-05-12, so the sample is
the whole current-regime population, not a convenience slice): under absolute caps, **64 of 80
(80 %)** would return HEALTHY; on the live slice since 01/08 (n=20, the week's alert mails),
**13 HEALTHY, 6 WARNING, 1 CRITICAL**.

## Follow-ups (out of scope)

1. **Persist `previous_total` and `coverage` in the BO** so the next calibration is possible. Its
   absence is exactly what blocked this one. Needs a migration — separate work.
2. `crawler-service/CLAUDE.md` documents neither the dual-mode breaker nor the health vocabulary,
   although the BO depends on that vocabulary. Add the verdict table
   (`HEALTHY`/`PENDING_SAMPLE`/`WARNING`/`CRITICAL`/`SUSPECT`/`ABORTED`) alongside the existing
   exit-code table, as the June spec did for `failure_cause`.
3. `id_previous_crawl` resolves for a small minority of BO rows, and some previous rows carry
   `urls_crawled = 0`. Unexplained; noticed while measuring, not investigated.
