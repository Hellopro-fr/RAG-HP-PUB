# BO (Marketplace PHP) — api-detection-langue-fr Caller Contract Design Spec

**Date:** 2026-04-27
**Status:** Draft (pending user review)
**Author:** Rindra + Claude
**Companion spec:** `docs/superpowers/specs/2026-04-20-detection-langue-fr-concurrency-defense-design.md`

## Problem Statement

The 2026-04-20 concurrency-defense work delivered a four-phase rollout:
- Phase 1 — `scraper.py` route handler leak fix.
- Phase 2 — Container limits + healthcheck + Prometheus metrics.
- Phase 3 — Admission middleware + inflight URL dedup.
- Phase 4 — Caller rollout to **`api-gateway`** and **`crawler-service`**.

Phase 4 explicitly scoped *two* known callers. A third caller — the **Marketplace PHP backoffice (BO)** — was not in scope at spec time. BO calls `api-detection-langue-fr` indirectly via `api.hellopro.eu` (the public api-gateway URL) from at least nine PHP callsites across cron orchestrators, on-demand scripts, and crawl-prep pipelines.

After the gateway change (`feat(api-gateway): add per-service downstream timeout map (detection=180s)` — commit `ba091eed`), BO's behavior degraded silently:

- **The gateway now returns `504` after 180s on detection calls** (was: infinite hang). BO's `CURLOPT_TIMEOUT=300` is no longer authoritative — the 180s ceiling fires first. BO scripts treat 504 as a generic failure with no retry.
- **The gateway now passes through `503` + `Retry-After` headers** from the saturated detection service (was: swallowed). BO has no 503-aware path; a 503 is treated as a generic failure that immediately throws `Exception`.
- **`detectBatchUrls()` calls `call_api_hellopro(..., timeout=0)`** — unlimited cURL timeout. With the gateway's new 180s cap, the unlimited timeout is ineffective on the wire but is also a misconfiguration that can mask future gateway changes.
- **No `CURLOPT_CONNECTTIMEOUT`** — slow DNS/SYN can consume the full request budget before a single byte is sent.
- **No retry, no `Retry-After` parsing, no exponential backoff** — under load BO callers will hammer the service with new requests instead of waiting per the server's guidance.

The crawler-service caller already adopted the contract (commit `238ab9d8`). BO is the last caller drifting from spec.

## Goals

- **Adopt the api-detection-langue-fr caller contract in BO** — same envelope (180s total, 10s connect, 503-only retries honoring `Retry-After`, exponential backoff fallback) used by crawler-service.
- **Surgical scope** — touch only detection-bound PHP code paths. Other gateway-relayed calls from BO (crawler, comparator, etc.) MUST be byte-identical post-merge.
- **Rollback granularity** — each commit revertable independently. No flag-day deployment.
- **Observable signal** — operators can see 503 retry events in the BO error log without enabling new infrastructure.
- **Future-proof signal channel** — pattern for capturing response headers (e.g. `Retry-After`, `X-RateLimit-*`) generalizable to other future contracts.

## Non-Goals

- **Cross-script concurrency cap.** PHP CLI/FPM workers are independent processes; in-process `Semaphore` from the Python contract has no equivalent without distributed state (Redis counter, MySQL row-lock). Multi-orchestrator overlap is theoretical until proven via 503 log patterns. Deferred.
- **Migrating BO to env-var-driven config.** Marketplace has no `.env` / dotenv convention for backoffice scripts. Constants in source file are sufficient and tunable via PR.
- **Adding PHPUnit / composer / CI test infra.** BO uses ponctuel scripts (`pct_*_rindra_BO.php`) as test surrogates. New toolchain is out of scope.
- **`/check-url` contract handling.** Inventory found zero BO callers. YAGNI.
- **Refactoring `call_api_hellopro` callers other than detection.** Six other services (crawler, comparator, etc.) currently call the wrapper; they remain on the legacy single-shot, no-retry path. Future per-service work, not this spec.

## Inventory of Affected BO Code

Found via ripgrep of `BO/` for `/api/v1/detect`, `/api/v1/detect-batch`, `detection_site_fr`, plus all callers of the local `detectBatchUrls()` helper:

| File | Callsite | Current path |
|---|---|---|
| `BO/admin/repertoire_test/moulinettes_interne/scrapping_produit_ia/fonctions/fonctions_scrapping.php` | `detectBatchUrls()` (line 7691) | central wrapper, calls `call_api_hellopro` with `timeout=0` |
| `BO/admin/repertoire_test/moulinettes_interne/scrapping_produit_ia/fonctions/fonctions_scrapping.php` | line 8411 | uses `detectBatchUrls()` (already through wrapper) |
| `BO/admin/repertoire_test/moulinettes_interne/scrapping_produit_ia/fonctions/fonctions_scrapping.php` | line 8503 | uses `detectBatchUrls()` (already through wrapper) |
| `BO/admin/repertoire_test/moulinettes_rindra/script_divers/ponctuel/roadmap_v1/pct_traitement_crawling_rindra_BO.php` | line 252 | uses `detectBatchUrls()` |
| `BO/admin/repertoire_test/moulinettes_interne/scrapping_produit_ia/script_identifier_site_fr_prospects_v2.php` | line 24 | uses `detectBatchUrls()` |
| `BO/admin/repertoire_test/moulinettes_interne/scrapping_produit_ia/script_identifier_site_fr_v2.php` | line 23 | uses `detectBatchUrls()` |
| `BO/admin/repertoire_test/moulinettes_interne/scrapping_produit_ia/script_find_variante_categorie_v2.php` | line 1234 | uses `detectBatchUrls()` |
| `BO/script/chatgpt/script_launch_crawl_csv.php` | `detectFrenchBatch()` (line 221) | **bypasses** `detectBatchUrls()` — direct `call_api_hellopro` to `/detect-batch` |
| `BO/script/chatgpt/script_launch_crawl_csv.php` | `detectFrenchSingle()` (line 251) | **bypasses** `detectBatchUrls()` — direct `call_api_hellopro` to `/detect` |

Six callsites are already routed through `detectBatchUrls()` — they pick up the contract for free once the wrapper is refactored. Two callsites in one file bypass the wrapper and must be migrated explicitly.

## Architectural Overview

Three coordinated edits across three files plus one new exception file:

```
┌─── Shared HTTP wrapper (additive only) ──────────────────────────┐
│                                                                  │
│   BO/fonctions/fonctions_hellopro.php                  [MODIFY]  │
│     • New optional &$responseHeaders out-param                   │
│     • New optional ?int $connectTimeout param                    │
│     • CURLOPT_HEADERFUNCTION callback unconditional but inert    │
│       for callers ignoring the out-param                         │
│     • All 6 untouched callsites byte-identical                   │
│                                                                  │
├─── Detection caller contract ────────────────────────────────────┤
│                                                                  │
│   .../scrapping_produit_ia/fonctions/                            │
│     DetectionApiException.php                          [NEW]     │
│       class DetectionApiException extends Exception              │
│       class DetectionApiBackpressureException                    │
│                                  extends DetectionApiException   │
│                                                                  │
│     fonctions_scrapping.php                            [MODIFY]  │
│       • DETECTION_REQUEST_TIMEOUT_S=180 const                    │
│       • DETECTION_CONNECT_TIMEOUT_S=10 const                     │
│       • DETECTION_MAX_RETRIES=2 const                            │
│       • DETECTION_BACKOFF_BASE_S=2 const                         │
│       • detectBatchUrls() rewritten as retry-loop wrapper        │
│         around the extended call_api_hellopro                    │
│       • require_once 'DetectionApiException.php' added           │
│                                                                  │
├─── Bypass migration (one script, two functions) ─────────────────┤
│                                                                  │
│   BO/script/chatgpt/script_launch_crawl_csv.php        [MODIFY]  │
│     • detectFrenchBatch() delegates to detectBatchUrls()         │
│     • detectFrenchSingle() delegates to detectBatchUrls(...,1)   │
│                                  with single-item list           │
│     • Local error_log on caught DetectionApiException            │
│                                                                  │
├─── Smoke verification (CLI-primary) ─────────────────────────────┤
│                                                                  │
│   .../moulinettes_rindra/script_divers/ponctuel/                 │
│     pct_smoke_detection_contract_rindra_BO.php         [NEW]     │
│       • CLI + browser dual-mode bootstrap                        │
│       • Test 1 happy path (live /detect-batch)                   │
│       • Test 2 503 backpressure (operator-coordinated)           │
│       • Test 3 exception hierarchy                               │
│       • Test 4 backward-compat call_api_hellopro signature       │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

The cURL plumbing stays in `call_api_hellopro` — single source of truth. Future TLS/proxy/auth changes propagate. The retry loop, contract constants, and exception throwing live in `detectBatchUrls`.

## Detailed Design

### 1 — Extended `call_api_hellopro` (additive)

`BO/fonctions/fonctions_hellopro.php` line 425. Two new optional trailing parameters:

```php
function call_api_hellopro(
    $method,
    $service,
    $endpoint,
    $payload = [],
    $isDownload = false,
    $timeout = 300,
    array &$responseHeaders = [],   // NEW: parsed lowercased headers, out-param
    ?int $connectTimeout = null     // NEW: explicit connect timeout (seconds), null = libcurl default
) {
    // ... existing body up to curl_setopt() block ...
    curl_setopt($ch, CURLOPT_TIMEOUT, $timeout);

    if ($connectTimeout !== null) {
        curl_setopt($ch, CURLOPT_CONNECTTIMEOUT, $connectTimeout);   // NEW
    }

    // NEW: capture response headers into out-param (lowercased keys)
    $responseHeaders = [];
    curl_setopt($ch, CURLOPT_HEADERFUNCTION, function ($_, $header) use (&$responseHeaders) {
        $colon = strpos($header, ':');
        if ($colon !== false) {
            $key = strtolower(trim(substr($header, 0, $colon)));
            $val = trim(substr($header, $colon + 1));
            $responseHeaders[$key] = $val;
        }
        return strlen($header);
    });

    // ... rest of function unchanged ...
}
```

**Backward-compatibility properties:**
- All existing callsites compile and behave identically (defaults preserve current contract).
- `&$responseHeaders` is an out-param ref; callers ignoring it see no observable change.
- `$connectTimeout = null` skips the `curl_setopt` call → libcurl default preserved.
- Header callback runs unconditionally but only writes to the out-param ref → zero observable side-effect for non-detection callers.

### 2 — Caller contract constants

Top of the detection section in `fonctions_scrapping.php`:

```php
// ─── api-detection-langue-fr caller contract ─────────────────────────────
// Mirrors RAG-HP-PUB spec docs/superpowers/specs/2026-04-20-detection-langue-fr-concurrency-defense-design.md
const DETECTION_REQUEST_TIMEOUT_S = 180;   // total request budget (matches gateway 180s ceiling)
const DETECTION_CONNECT_TIMEOUT_S = 10;    // TCP connect cap
const DETECTION_MAX_RETRIES       = 2;     // 503-only retry count
const DETECTION_BACKOFF_BASE_S    = 2;     // exponential backoff base when Retry-After header is absent
```

**Rationale for constant choice over env vars:** Marketplace BO has no dotenv / runtime-config infra for PHP. Constants are tunable via PR, version-controlled, and grep-able. Future migration to env vars is a follow-up if ops infrastructure supports it.

### 3 — Refactored `detectBatchUrls()`

Signature, return type, and parameter order preserved. Six existing callers untouched.

```php
function detectBatchUrls(array $items, int $maxConcurrency = 10, string $mode = 'complete', bool $force_redetect = false): ?array
{
    $items = sanitizeUtf8Recursive($items);
    $payload = [
        'items'           => $items,
        'max_concurrency' => $maxConcurrency,
        'mode'            => $mode,
        'force_refresh'   => $force_redetect,
    ];

    for ($attempt = 0; $attempt <= DETECTION_MAX_RETRIES; $attempt++) {
        $headers = [];
        $result = call_api_hellopro(
            'POST',
            'detection_site_fr-service',
            '/api/v1/detect-batch',
            $payload,
            false,
            DETECTION_REQUEST_TIMEOUT_S,
            $headers,
            DETECTION_CONNECT_TIMEOUT_S
        );

        $isError = is_array($result) && isset($result['success']) && $result['success'] === false;
        if (!$isError) {
            return $result;
        }

        $httpCode = (int) ($result['http_code'] ?? 0);

        if ($httpCode === 503) {
            if ($attempt >= DETECTION_MAX_RETRIES) {
                error_log("[detection-langue-fr] 503 retries exhausted for batch of " . count($items) . " items");
                throw new DetectionApiBackpressureException(
                    "detect-batch backpressure: 503 after " . (DETECTION_MAX_RETRIES + 1) . " attempts"
                );
            }
            $retryAfterRaw = $headers['retry-after'] ?? null;
            $retryAfter = $retryAfterRaw !== null ? (float) $retryAfterRaw : null;
            $waitS = $retryAfter ?? (DETECTION_BACKOFF_BASE_S * (2 ** $attempt));
            error_log(
                "[detection-langue-fr] 503 received, retry " . ($attempt + 1) . "/" . DETECTION_MAX_RETRIES
                . " after {$waitS}s (Retry-After=" . ($retryAfterRaw ?? 'absent') . ")"
            );
            usleep((int) ($waitS * 1_000_000));
            continue;
        }

        throw new DetectionApiException(
            "detect-batch failed: HTTP {$httpCode}: " . ($result['message'] ?? 'unknown')
        );
    }

    throw new DetectionApiException("detect-batch retry loop exited without result");
}
```

**Invariants:**
- 2xx fast path: single curl call, no retry overhead.
- `error_log` only on 503 and exhaustion paths — zero noise on happy path.
- `usleep` for sub-second precision (handles fractional `Retry-After`).
- Wait precedence: `Retry-After` > `DETECTION_BACKOFF_BASE_S * 2**attempt`.
- Retries fire only on HTTP 503; transport errors and other status codes throw immediately.

### 4 — Exception hierarchy

`BO/admin/repertoire_test/moulinettes_interne/scrapping_produit_ia/fonctions/DetectionApiException.php` (new):

```php
<?php
/**
 * Typed exceptions for api-detection-langue-fr caller contract.
 *
 * Hierarchy:
 *   Exception
 *     └── DetectionApiException                  : transport, 4xx, non-503 5xx, JSON decode failures
 *           └── DetectionApiBackpressureException : 503 + Retry-After exhausted after DETECTION_MAX_RETRIES
 *
 * Existing `catch (Exception $e)` blocks still trigger (subclass).
 * New callsites can opt into differentiated handling:
 *   try { ... }
 *   catch (DetectionApiBackpressureException $e) { /* reschedule next cron */ }
 *   catch (DetectionApiException $e)             { /* log + skip batch */ }
 */
class DetectionApiException extends Exception {}
class DetectionApiBackpressureException extends DetectionApiException {}
```

Loaded once at top of `fonctions_scrapping.php`:

```php
require_once __DIR__ . '/DetectionApiException.php';
```

### 5 — Migration of `script_launch_crawl_csv.php`

Two local helpers currently bypass the central wrapper. Refactor both to delegate.

**`detectFrenchBatch()` line 221:**

```php
function detectFrenchBatch(array $urls): array
{
    $items = array_map(fn($url) => ['url' => $url], $urls);

    try {
        $response = detectBatchUrls($items, BATCH_SIZE, 'complete', false);
    } catch (DetectionApiBackpressureException $e) {
        error_log("[script_launch_crawl_csv] backpressure on batch of " . count($urls) . " URLs: " . $e->getMessage());
        return [];
    } catch (DetectionApiException $e) {
        error_log("[script_launch_crawl_csv] detection batch failed: " . $e->getMessage());
        return [];
    }

    $results = [];
    if (!empty($response['results'])) {
        foreach ($response['results'] as $index => $result) {
            $url = $urls[$index] ?? '';
            $results[$url] = $result;
        }
    }
    return $results;
}
```

**`detectFrenchSingle()` line 251:**

```php
function detectFrenchSingle(string $url): ?array
{
    try {
        $response = detectBatchUrls([['url' => $url]], 1, 'complete', false);
    } catch (DetectionApiException $e) {
        error_log("[script_launch_crawl_csv] detection single failed for {$url}: " . $e->getMessage());
        return null;
    }
    return $response['results'][0] ?? null;
}
```

**Pre-flight verification during implementation:**
- Confirm `script_launch_crawl_csv.php` already requires `fonctions_scrapping.php` via its include chain. If not — add `require_once`.
- Confirm `use_nlp_detection=true` is the server's default for `mode=complete` (read service code or contract). Two choices:
  - **(a)** Add `$useNlp = true` param to `detectBatchUrls()` (additive, default-on).
  - **(b)** Drop the redundant flag — server defaults `use_nlp_detection=true` for `mode=complete`.
  - Recommend (b) unless an explicit `false` callsite is found.

### 6 — Smoke verification script

`BO/admin/repertoire_test/moulinettes_rindra/script_divers/ponctuel/pct_smoke_detection_contract_rindra_BO.php` (new). CLI-primary, browser-fallback dual-mode.

```php
<?php
$is_cli = (php_sapi_name() === 'cli');

if (!$is_cli) {
    set_time_limit(300);
    ini_set('max_execution_time', '300');
    header('Content-Type: text/plain; charset=utf-8');
    // Auth gate path — verify during implementation against BO ponctuel sibling scripts
    // require_once __DIR__ . '/../../../../include/<auth_gate>.php';
}

require_once __DIR__ . '/../../../../moulinettes_interne/scrapping_produit_ia/fonctions/fonctions_scrapping.php';

// Test 1 — happy path
$result = detectBatchUrls([['url' => 'https://www.lemonde.fr']], 1, 'complete', false);
assert(!empty($result['results'][0]['ok']), 'happy path should classify lemonde.fr as ok');
echo "✓ Test 1 happy path\n";

// Test 2 — 503 backpressure (operator-coordinated; skipped if server not saturated)
try {
    detectBatchUrls([['url' => 'https://www.example.com']], 1, 'complete', false);
    echo "⚠ Test 2 skipped (server not saturated)\n";
} catch (DetectionApiBackpressureException $e) {
    echo "✓ Test 2 backpressure exception thrown: " . $e->getMessage() . "\n";
}

// Test 3 — exception hierarchy
assert(is_a('DetectionApiBackpressureException', 'DetectionApiException', true));
assert(is_a('DetectionApiException', 'Exception', true));
echo "✓ Test 3 exception hierarchy\n";

// Test 4 — backward-compat call_api_hellopro signature
$res = call_api_hellopro('GET', 'detection_site_fr-service', '/api/v1/health', [], false, 30);
assert(is_array($res));
echo "✓ Test 4 backward-compat signature\n";

echo "\nAll smoke checks passed.\n";
```

Run modes:
- **CLI (primary):** `php pct_smoke_detection_contract_rindra_BO.php` — recommended for Test 2 (no PHP-FPM `max_execution_time` constraint).
- **Browser:** `https://bo.../pct_smoke_detection_contract_rindra_BO.php` — happy-path + Test 4 only; Test 2 risky under PHP-FPM timeout.

## Configuration Reference

All knobs live as PHP constants in `fonctions_scrapping.php`. Tunable via PR + redeploy.

| Constant | Default | Purpose |
|---|---|---|
| `DETECTION_REQUEST_TIMEOUT_S` | `180` | Total request budget — matches gateway downstream cap |
| `DETECTION_CONNECT_TIMEOUT_S` | `10` | TCP connect ceiling |
| `DETECTION_MAX_RETRIES` | `2` | 503-only retry count (3 attempts total) |
| `DETECTION_BACKOFF_BASE_S` | `2` | Exponential backoff base when `Retry-After` header is absent |

## Testing Strategy

Marketplace BO has no PHPUnit / composer / CI test infra. Smoke verification script is the canonical regression check.

### Pre-merge manual checklist

| # | Check | How |
|---|---|---|
| 1 | Smoke script Tests 1, 3, 4 green | `php pct_smoke_detection_contract_rindra_BO.php` (CLI) |
| 2 | Constants resolve | quick `php -r 'require ...; var_dump(DETECTION_REQUEST_TIMEOUT_S);'` |
| 3 | `script_launch_crawl_csv.php` end-to-end on a small CSV (5–10 URLs) | run script in staging |
| 4 | One `detectBatchUrls` orchestrator unaffected | run `pct_traitement_crawling_rindra_BO.php` in TTL-filtered mode if available |
| 5 | `error_log` shows no spurious noise on happy path | tail BO error log during Test 1 |
| 6 | New typed exceptions catchable as `Exception` (subclass) | smoke Test 3 |

### 503 path (operator-coordinated, optional)

**Strategy A — preferred:** Ops temporarily sets `ADMISSION_MAX_SLOTS=0` on `api-detection-langue-fr-service` for ~30s. During window, run smoke script Test 2. Restore env afterwards. Confirms real header parsing on real network path.

**Strategy B — fallback:** Add a temporary single-line debug branch in `detectBatchUrls()` keyed on `getenv('DETECTION_FORCE_503')` that synthesizes a 503 without hitting the network. Removed before merge. Use only if ops won't coordinate.

If neither strategy is run, production traffic will eventually exercise the 503 path; logging will surface it.

## Rollout

### Commit decomposition (FR-only per session preference)

Five commits, ordered by ascending blast radius. Each commit revertable independently.

| # | Type | Files | Why isolated |
|---|---|---|---|
| 1 | `feat(detection)` | `BO/admin/.../fonctions/DetectionApiException.php` (new) | Class declarations only — zero side-effect |
| 2 | `feat(call_api_hellopro)` | `BO/fonctions/fonctions_hellopro.php` | Additive signature change; backward-compat verified by 6 untouched callsites |
| 3 | `feat(detection)` | `BO/admin/.../fonctions_scrapping.php` (constants + `detectBatchUrls()` rewrite + `require_once`) | Behavior change — 503 retry, 180s timeout, typed exceptions |
| 4 | `refactor(script_launch_crawl_csv)` | `BO/script/chatgpt/script_launch_crawl_csv.php` | Migrate `detectFrenchBatch` + `detectFrenchSingle` to wrapper |
| 5 | `chore(ponctuel)` | `BO/admin/.../pct_smoke_detection_contract_rindra_BO.php` (new) | Smoke script only — no production path |

### Deploy sequence

1. Push commit 1 — no behavior change.
2. Push commit 2 — backward-compat. Spot-check one existing crawler/comparator call to confirm zero regression.
3. Push commit 3 — first behavior change. Run smoke Tests 1 + 4 in CLI.
4. Push commit 4 — run a small CSV (5–10 URLs) through `script_launch_crawl_csv.php`.
5. Push commit 5 — keep smoke script in repo for future regressions.

**Smoke gate after step 3:** `error_log` shows no spurious 503 messages on a single happy `/detect-batch` call AND result shape is unchanged.

**Smoke gate after step 4:** CSV run completes with same outcome distribution as prior runs (same proportion of `ok=true` / `ok=false`).

### Rollback

Per-commit `git revert`. No flag/config kill-switch — contract is hardcoded constants.

| Failure signal | Rollback |
|---|---|
| Crawler/comparator caller breaks (commit 2 regression) | revert commit 2 — restores wrapper signature |
| Detection batches fail where they used to succeed | revert commit 3 |
| `script_launch_crawl_csv` produces wrong CSV output | revert commit 4 |
| Cascading | revert in reverse order: 4 → 3 → 2 |

Each revert is single-file (commits 1, 3, 4, 5) or single-function (commit 2). No DB migrations, no infra changes.

### Operator coordination

For 503-path verification only (Strategy A above): one-time ~5 min ops window to flip `ADMISSION_MAX_SLOTS=0` and back. Skippable.

## Success Criteria

- All 8 existing detection callsites (6 routed through `detectBatchUrls()` + 2 migrated bypasses in `script_launch_crawl_csv.php`) continue working byte-identical on happy path (regression check via smoke step 4).
- New `error_log` lines `[detection-langue-fr] ...` appear ONLY on actual 503 events from server (zero noise on 2xx).
- Under induced 503 (Strategy A), wait time matches `Retry-After` header within 100 ms.
- `DetectionApiBackpressureException` thrown when retries exhausted; caught cleanly by existing `catch (Exception)` blocks (no fatal errors).
- `call_api_hellopro` callers other than detection (crawler, comparator, etc.) show zero behavior change in their logs.
- `script_launch_crawl_csv.php` end-to-end run on staging produces same outcome distribution as pre-refactor baseline.

## Follow-Up Considerations

### Cross-script concurrency cap (scope B in original brainstorming)

Defer until 503 log patterns prove multi-orchestrator overlap is real. Implementation options when needed:
- Redis `INCR`/`DECR` counter with TTL fallback (matches the `crawl_jobs:running_count` pattern).
- MySQL row-lock counter row.
- File-based mutex via `flock` (process-local only — incomplete if multiple PHP processes run on different hosts).

### Migration to env-var-driven config

Defer until BO ops infrastructure supports `.env` for PHP backoffice. Then mirror the RAG-HP-PUB pattern: `getenv('DETECTION_REQUEST_TIMEOUT_S')` with constant fallback.

### `/check-url` contract

No current BO callers found. Add only when a caller appears.

### Per-callsite differentiated handling of `DetectionApiBackpressureException`

Typed exception is in place. Callers can opt into smarter behavior (e.g. cron reschedule) without changing the wrapper. Add per-callsite as needs arise.

### `DETECTION_MAX_CONCURRENCY` semantics in PHP

Concurrency cap is per-process. Within a single sequential CLI/FPM script the value is implicitly 1. Cross-process cap is the deferred follow-up above.
