# BO (Marketplace PHP) — api-detection-langue-fr Caller Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring the Marketplace BO (PHP) caller of `api-detection-langue-fr` into compliance with the caller contract enforced by `api-gateway` (commit `ba091eed`) and already adopted by `crawler-service` (commit `238ab9d8`).

**Architecture:** Three layers of edits in the BO repo (root: `D:\DevHellopro\Marketplace`):
1. Additive extension of the shared HTTP wrapper `call_api_hellopro` to expose response headers + a connect-timeout knob — backward-compatible with all six existing non-detection callers.
2. New typed exception hierarchy + retry-loop refactor of `detectBatchUrls()` honoring `Retry-After` and exponential backoff. 180s total / 10s connect, retries only on HTTP 503.
3. Migration of two bypass functions in `script_launch_crawl_csv.php` to delegate to `detectBatchUrls()`. Smoke verification script for CLI + browser.

**Tech Stack:** PHP 7.4+ (cURL, native classes), no PHPUnit / composer / dotenv. BO ponctuel scripts (`pct_*_rindra_BO.php`) used as test surrogates.

**Spec:** `docs/superpowers/specs/2026-04-27-detection-langue-fr-bo-caller-contract-design.md` (RAG-HP-PUB commit `97ff1555`).

**Companion spec:** `docs/superpowers/specs/2026-04-20-detection-langue-fr-concurrency-defense-design.md`.

**Repository note:** All implementation commits land in `D:\DevHellopro\Marketplace` (master branch by convention, FR-only commit messages per session preference). The plan document lives in RAG-HP-PUB alongside the spec.

---

## File Structure

| File | Status | Responsibility |
|---|---|---|
| `D:\DevHellopro\Marketplace\BO\admin\repertoire_test\moulinettes_interne\scrapping_produit_ia\fonctions\DetectionApiException.php` | NEW | Typed exception hierarchy: `DetectionApiException`, `DetectionApiBackpressureException` |
| `D:\DevHellopro\Marketplace\BO\fonctions\fonctions_hellopro.php` | MODIFY (additive) | Extend `call_api_hellopro` signature with `&$responseHeaders` + `?int $connectTimeout`; add `CURLOPT_HEADERFUNCTION` capture; conditional `CURLOPT_CONNECTTIMEOUT` |
| `D:\DevHellopro\Marketplace\BO\admin\repertoire_test\moulinettes_interne\scrapping_produit_ia\fonctions\fonctions_scrapping.php` | MODIFY | Contract constants block; `require_once` for new exception file; full rewrite of `detectBatchUrls()` (line 7691) as retry-loop wrapper around extended `call_api_hellopro` |
| `D:\DevHellopro\Marketplace\BO\script\chatgpt\script_launch_crawl_csv.php` | MODIFY | Migrate `detectFrenchBatch()` (line 221) + `detectFrenchSingle()` (line 251) to delegate to `detectBatchUrls()`; wrap with typed catches |
| `D:\DevHellopro\Marketplace\BO\admin\repertoire_test\moulinettes_rindra\script_divers\ponctuel\pct_smoke_detection_contract_rindra_BO.php` | NEW | CLI + browser smoke script: happy path, 503 backpressure (operator-coordinated), exception hierarchy, backward-compat |

**Files NOT touched (zero blast radius targets):**
- All 6 existing `call_api_hellopro` callers other than detection (crawler, comparator, etc.).
- 5 existing `detectBatchUrls()` callsites (`fonctions_scrapping.php:8411`, `:8503`; `pct_traitement_crawling_rindra_BO.php:252`; `script_identifier_site_fr_prospects_v2.php:24`; `script_identifier_site_fr_v2.php:23`; `script_find_variante_categorie_v2.php:1234`) — they pick up the new contract for free.

---

## Task 0: Pre-Flight Verification

**Goal:** Resolve three implementation-time unknowns flagged by the spec before writing any code.

**Files:**
- Read: `D:\DevHellopro\Marketplace\BO\script\chatgpt\script_launch_crawl_csv.php` (top — include chain)
- Read: `D:\DevHellopro\Marketplace\BO\admin\repertoire_test\moulinettes_interne\scrapping_produit_ia\fonctions\fonctions_scrapping.php` (require_once block at top)
- Read sibling: `D:\DevHellopro\Marketplace\BO\admin\repertoire_test\moulinettes_rindra\script_divers\ponctuel\` (any existing `pct_*_rindra_BO.php` for auth gate convention)
- Search: all 8 `detectBatchUrls()` callsites for explicit `use_nlp_detection=false`
- Search: all 6 existing `call_api_hellopro` callers across BO (sanity baseline before extending)

**Acceptance Criteria:**
- [ ] Confirmed whether `script_launch_crawl_csv.php` already requires `fonctions_scrapping.php` (transitively or directly). Recorded the include chain.
- [ ] Confirmed whether any existing caller of `detectBatchUrls()` or local helpers uses `use_nlp_detection=false`. If none, decision (b) from spec § 4.2 is locked in.
- [ ] Recorded the auth-gate path used by sibling BO ponctuel scripts (e.g. `require_once 'BO/include/...'`) for use in Task 5.
- [ ] Recorded the count and locations of all 6 non-detection callers of `call_api_hellopro` to establish backward-compat baseline (Task 2 spot-check list).

**Verify:** Findings written to a temporary scratch file `D:\DevHellopro\Marketplace\temp\preflight_detection_contract.md`. The file is consumed by later tasks and discarded post-merge.

**Steps:**

- [ ] **Step 1: Read the top of `script_launch_crawl_csv.php` to inspect its include chain**

```bash
# Read first 60 lines for require_once / include statements
head -n 60 'D:/DevHellopro/Marketplace/BO/script/chatgpt/script_launch_crawl_csv.php'
```

If `fonctions_scrapping.php` is not directly required, follow each `require`/`include` to its target and grep that file for a transitive require. Record the chain.

- [ ] **Step 2: Read the `require_once` block at top of `fonctions_scrapping.php`**

```bash
# Read first 100 lines to see require_once style + path conventions
head -n 100 'D:/DevHellopro/Marketplace/BO/admin/repertoire_test/moulinettes_interne/scrapping_produit_ia/fonctions/fonctions_scrapping.php'
```

Note the indentation, quoting style, and `__DIR__` usage so the new `require_once` for `DetectionApiException.php` matches.

- [ ] **Step 3: Search BO for `use_nlp_detection` usage to confirm spec assumption (b)**

Use the Grep tool:
```
pattern: use_nlp_detection
glob: BO/**/*.php
output_mode: content
-n: true
```

Expected: no callsite passes `use_nlp_detection=false` for `mode='complete'`. If any does → switch to spec § 4.2 option (a) (add `$useNlp` param to `detectBatchUrls()`) and revise Task 3.

- [ ] **Step 4: Inspect existing BO ponctuel scripts for the auth-gate convention**

```bash
ls 'D:/DevHellopro/Marketplace/BO/admin/repertoire_test/moulinettes_rindra/script_divers/ponctuel/' | head -20
```

Pick 2 sibling `pct_*_rindra_BO.php` files. Read their top 40 lines to see the auth-gate `require_once` (typical pattern: a session-check include). Record the exact relative path.

- [ ] **Step 5: Find and list the 6 non-detection callers of `call_api_hellopro`**

Use the Grep tool:
```
pattern: call_api_hellopro\s*\(
glob: BO/**/*.php
output_mode: content
-n: true
```

Filter out the wrapper definition itself (one line in `BO/fonctions/fonctions_hellopro.php`). Filter out callers using service `'detection_site_fr-service'`. The remainder is the backward-compat baseline. Record file paths + line numbers.

- [ ] **Step 6: Write findings to `D:\DevHellopro\Marketplace\temp\preflight_detection_contract.md`**

Use the Write tool to create the file with this template:
```markdown
# Pre-Flight Findings — Detection Caller Contract

## 1. Include chain for script_launch_crawl_csv.php
- Direct requires: <list>
- Transitive path to fonctions_scrapping.php: <yes/no, chain>
- Action: <"no change needed" | "add require_once at top of script_launch_crawl_csv.php">

## 2. use_nlp_detection callsites
- Files passing `use_nlp_detection=false`: <list, or "none">
- Decision (a/b): <b — drop redundant flag | a — add $useNlp param to detectBatchUrls>

## 3. BO ponctuel auth gate convention
- Sibling pct_*_rindra_BO.php example: <path>
- Auth gate require: `require_once <path>;`
- Smoke script auth gate path (relative to its own location): <path>

## 4. Non-detection callers of call_api_hellopro (backward-compat baseline)
1. <file:line> — service: <service>
2. <file:line> — service: <service>
... etc
Total: <N>
```

- [ ] **Step 7: No commit (read-only task)**

`temp/preflight_detection_contract.md` is in `temp/` which should be gitignored (verify; if not, prefix path with `D:\DevHellopro\Marketplace\.gitignore`-aware location). No `git add`.

---

## Task 1: Add Exception Classes

**Goal:** Create the typed exception hierarchy used by `detectBatchUrls()` and downstream callers.

**Files:**
- Create: `D:\DevHellopro\Marketplace\BO\admin\repertoire_test\moulinettes_interne\scrapping_produit_ia\fonctions\DetectionApiException.php`

**Acceptance Criteria:**
- [ ] File exists at the exact path above.
- [ ] PHP syntax check passes (`php -l`).
- [ ] Two classes declared: `DetectionApiException` (extends `Exception`) and `DetectionApiBackpressureException` (extends `DetectionApiException`).
- [ ] File doc comment present documenting the hierarchy and intended use.
- [ ] No constructor / no extra fields (YAGNI per spec).

**Verify:** `php -l 'D:/DevHellopro/Marketplace/BO/admin/repertoire_test/moulinettes_interne/scrapping_produit_ia/fonctions/DetectionApiException.php'` → output `No syntax errors detected in <path>`.

**Steps:**

- [ ] **Step 1: Write the new file**

Use the Write tool with `file_path = D:\DevHellopro\Marketplace\BO\admin\repertoire_test\moulinettes_interne\scrapping_produit_ia\fonctions\DetectionApiException.php` and content:

```php
<?php
/**
 * Typed exceptions for the api-detection-langue-fr caller contract.
 *
 * Hierarchy:
 *   Exception
 *     └── DetectionApiException                  : transport, 4xx, non-503 5xx, JSON decode failures
 *           └── DetectionApiBackpressureException : 503 + Retry-After exhausted after DETECTION_MAX_RETRIES
 *
 * Existing `catch (Exception $e)` blocks still trigger via subclass.
 *
 * New callsites can opt into differentiated handling:
 *   try {
 *       $r = detectBatchUrls(...);
 *   } catch (DetectionApiBackpressureException $e) {
 *       // reschedule on next cron run
 *   } catch (DetectionApiException $e) {
 *       // log + skip batch
 *   }
 */

class DetectionApiException extends Exception {}

class DetectionApiBackpressureException extends DetectionApiException {}
```

- [ ] **Step 2: Run PHP syntax check**

```bash
php -l 'D:/DevHellopro/Marketplace/BO/admin/repertoire_test/moulinettes_interne/scrapping_produit_ia/fonctions/DetectionApiException.php'
```

Expected output: `No syntax errors detected in D:/DevHellopro/Marketplace/BO/admin/repertoire_test/moulinettes_interne/scrapping_produit_ia/fonctions/DetectionApiException.php`

If the output contains `Parse error` or `Errors parsing`, fix the file and re-run before proceeding.

- [ ] **Step 3: Stage and commit**

```bash
cd 'D:/DevHellopro/Marketplace'
git add 'BO/admin/repertoire_test/moulinettes_interne/scrapping_produit_ia/fonctions/DetectionApiException.php'
git status
```

Confirm `git status` shows exactly one new file staged.

```bash
git commit -m "$(cat <<'EOF'
feat(detection): exceptions typées pour contrat caller detection-langue-fr

Ajoute DetectionApiException + DetectionApiBackpressureException
utilisées par le contrat caller api-detection-langue-fr (spec
2026-04-27-detection-langue-fr-bo-caller-contract-design.md).

DetectionApiBackpressureException est levée quand les retries
sur HTTP 503 sont épuisés. DetectionApiException couvre tout
autre échec (transport, 4xx, 5xx hors 503, décodage JSON).
Hérite d'Exception donc les catch existants restent compatibles.
EOF
)"
git status
```

Expected: `working tree clean` (modulo files unrelated to this task).

---

## Task 2: Extend `call_api_hellopro` (Additive)

**Goal:** Add response-header capture + optional connect timeout to the shared HTTP wrapper without changing any existing caller's behavior.

**Files:**
- Modify: `D:\DevHellopro\Marketplace\BO\fonctions\fonctions_hellopro.php` lines 425–491 (function body)

**Acceptance Criteria:**
- [ ] Signature gains two trailing optional params: `array &$responseHeaders = []` and `?int $connectTimeout = null`.
- [ ] `CURLOPT_HEADERFUNCTION` callback added; populates `$responseHeaders` with lowercased key → trimmed value pairs.
- [ ] `CURLOPT_CONNECTTIMEOUT` set ONLY when `$connectTimeout !== null` (libcurl default preserved otherwise).
- [ ] Existing function body (URL build, GET query string, POST/PUT/DELETE body, error handling, `$isDownload` branch, JSON decode) byte-identical except for the three additions above.
- [ ] PHP syntax check passes.
- [ ] All 6 non-detection callsites identified in Task 0 still pass `php -l` on their respective files (signature is additive, no callsite needs changes).

**Verify:**
```bash
php -l 'D:/DevHellopro/Marketplace/BO/fonctions/fonctions_hellopro.php'
```
→ `No syntax errors detected in <path>`. Then sample-lint each of the 6 non-detection caller files from Task 0 finding §4.

**Steps:**

- [ ] **Step 1: Read the current function**

Use the Read tool on `D:\DevHellopro\Marketplace\BO\fonctions\fonctions_hellopro.php` with `offset=425, limit=70`. Confirm the body matches the spec § 1 reference (this baseline was inspected during brainstorming — re-confirm in case the file moved).

- [ ] **Step 2: Edit the signature**

Use the Edit tool. Replace the function definition line to add the two trailing parameters.

`old_string`:
```php
function call_api_hellopro($method, $service, $endpoint, $payload = [], $isDownload = false, $timeout = 300)
{
	$baseUrl = 'https://api.hellopro.eu/' . $service;
```

`new_string`:
```php
function call_api_hellopro(
	$method,
	$service,
	$endpoint,
	$payload = [],
	$isDownload = false,
	$timeout = 300,
	array &$responseHeaders = [],
	?int $connectTimeout = null
)
{
	$baseUrl = 'https://api.hellopro.eu/' . $service;
```

- [ ] **Step 3: Insert the connect-timeout opt-in + header capture, immediately after the existing `CURLOPT_TIMEOUT` line**

Use the Edit tool.

`old_string`:
```php
	curl_setopt($ch, CURLOPT_URL, $url);
	curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
	curl_setopt($ch, CURLOPT_TIMEOUT, $timeout);

	if (in_array($method, ['POST', 'PUT', 'DELETE'])) {
```

`new_string`:
```php
	curl_setopt($ch, CURLOPT_URL, $url);
	curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
	curl_setopt($ch, CURLOPT_TIMEOUT, $timeout);

	if ($connectTimeout !== null) {
		curl_setopt($ch, CURLOPT_CONNECTTIMEOUT, $connectTimeout);
	}

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

	if (in_array($method, ['POST', 'PUT', 'DELETE'])) {
```

- [ ] **Step 4: PHP syntax check the wrapper**

```bash
php -l 'D:/DevHellopro/Marketplace/BO/fonctions/fonctions_hellopro.php'
```

Expected: `No syntax errors detected in <path>`.

- [ ] **Step 5: Spot-check 3 non-detection callers compile (backward-compat verification)**

Pick the 3 most-trafficked callers from Task 0 finding §4 and run `php -l` on each:

```bash
php -l '<caller-file-1>'
php -l '<caller-file-2>'
php -l '<caller-file-3>'
```

Expected: all three return `No syntax errors detected`. (Default values on the new params guarantee this — failure here means the signature is malformed.)

- [ ] **Step 6: Stage and commit**

```bash
cd 'D:/DevHellopro/Marketplace'
git add 'BO/fonctions/fonctions_hellopro.php'
git diff --cached --stat
```

Expected: `1 file changed, ~17 insertions(+), 1 deletion(-)`.

```bash
git commit -m "$(cat <<'EOF'
feat(call_api_hellopro): expose response headers + connect timeout

Ajoute deux paramètres optionnels à call_api_hellopro:
- &$responseHeaders (out-param) capturé via CURLOPT_HEADERFUNCTION
  avec clés en minuscules
- ?int $connectTimeout (null = défaut libcurl préservé)

Changement strictement additif: les six callers existants non-
detection continuent de fonctionner à l'identique. Préparation
pour le contrat caller api-detection-langue-fr qui a besoin de
lire l'en-tête Retry-After et d'imposer un connect timeout
explicite (spec 2026-04-27-detection-langue-fr-bo-caller-contract-design.md).
EOF
)"
git status
```

---

## Task 3: Refactor `detectBatchUrls()` + Constants + `require_once`

**Goal:** Replace `detectBatchUrls()` body with a retry-loop wrapper that enforces the caller contract: 180s/10s timeouts, 503-only retries honoring `Retry-After`, exponential backoff, typed exceptions, observable `error_log` lines.

**Files:**
- Modify: `D:\DevHellopro\Marketplace\BO\admin\repertoire_test\moulinettes_interne\scrapping_produit_ia\fonctions\fonctions_scrapping.php`
  - Add `require_once` near the existing requires block at top (path inferred in Task 0 step 2).
  - Add 4 contract constants near the top of the detection helpers section (just above `detectBatchUrls()` at line 7691, OR alongside other detection-domain helpers — adjust based on file layout from Task 0).
  - Rewrite `detectBatchUrls()` (lines 7691–7713).

**Acceptance Criteria:**
- [ ] `require_once __DIR__ . '/DetectionApiException.php';` added once near the top of the file.
- [ ] 4 constants declared: `DETECTION_REQUEST_TIMEOUT_S=180`, `DETECTION_CONNECT_TIMEOUT_S=10`, `DETECTION_MAX_RETRIES=2`, `DETECTION_BACKOFF_BASE_S=2`.
- [ ] `detectBatchUrls()` signature unchanged: `(array $items, int $maxConcurrency = 10, string $mode = 'complete', bool $force_redetect = false): ?array`.
- [ ] Retry loop fires up to `DETECTION_MAX_RETRIES + 1 = 3` attempts (initial + 2 retries) on HTTP 503.
- [ ] On 503 with `Retry-After` header → wait `$retryAfter` seconds. On 503 without header → wait `DETECTION_BACKOFF_BASE_S * 2 ** $attempt` seconds.
- [ ] Final 503 → throw `DetectionApiBackpressureException`.
- [ ] Non-503 error (transport, 4xx, 5xx other) → throw `DetectionApiException`.
- [ ] 2xx success returns the decoded array unchanged.
- [ ] `error_log` calls fire ONLY on 503 retry + on retry exhaustion (zero noise on 2xx).
- [ ] PHP syntax check passes.
- [ ] All 5 untouched callsites of `detectBatchUrls()` still PHP-lint clean.

**Verify:**
```bash
php -l 'D:/DevHellopro/Marketplace/BO/admin/repertoire_test/moulinettes_interne/scrapping_produit_ia/fonctions/fonctions_scrapping.php'
```
→ `No syntax errors detected`. Then sanity-lint the 5 untouched callsite files.

**Steps:**

- [ ] **Step 1: Add `require_once` near top of the file**

Use the Edit tool. Locate the existing `require_once` block (per Task 0 step 2) and insert one new line right after the last existing `require_once`. Match the existing indentation/quoting style.

Example (adjust to match the actual block found in Task 0):

`old_string`:
```php
require_once __DIR__ . '/some_existing_helper.php';
```

`new_string`:
```php
require_once __DIR__ . '/some_existing_helper.php';
require_once __DIR__ . '/DetectionApiException.php';
```

(Replace `some_existing_helper.php` with the actual last sibling require found in Task 0.)

- [ ] **Step 2: Add the contract constants block immediately above `detectBatchUrls()` (line 7691)**

Use the Edit tool.

`old_string`:
```php
/**
 * Détecte des informations sur un lot d'URLs via l'API HelloPro
 *
 * @param array $items Tableau des items à analyser (chaque item contient 'url' et optionnellement 'html_content')
 * @param int $maxConcurrency Nombre maximum de requêtes concurrentes (par défaut: 10)
 * @param string $mode Mode de détection: 'complete' ou autre (par défaut: 'complete')
 * @param bool $force_redetect Force la redétection des informations en écrasant les informations dans Redis si disponible (par défaut: false)
 * @return array|null Résultat de l'API ou null en cas d'erreur
 * @throws Exception Si la requête échoue
 */
function detectBatchUrls(array $items, int $maxConcurrency = 10, string $mode = 'complete', bool $force_redetect = false): ?array
```

`new_string`:
```php
// ─── api-detection-langue-fr caller contract ─────────────────────────────
// Mirrors RAG-HP-PUB spec docs/superpowers/specs/2026-04-27-detection-langue-fr-bo-caller-contract-design.md
// Companion: docs/superpowers/specs/2026-04-20-detection-langue-fr-concurrency-defense-design.md
const DETECTION_REQUEST_TIMEOUT_S = 180;   // total request budget (matches gateway 180s ceiling)
const DETECTION_CONNECT_TIMEOUT_S = 10;    // TCP connect cap
const DETECTION_MAX_RETRIES       = 2;     // 503-only retry count (3 attempts total)
const DETECTION_BACKOFF_BASE_S    = 2;     // exponential backoff base when Retry-After header is absent

/**
 * Détecte des informations sur un lot d'URLs via l'API HelloPro
 *
 * Implémente le contrat caller api-detection-langue-fr:
 *   - Timeout total 180s, connect 10s
 *   - Retry sur HTTP 503 uniquement, max 2 retries
 *   - Wait précédence: header Retry-After > backoff exponentiel
 *
 * @param array $items Tableau des items à analyser (chaque item contient 'url' et optionnellement 'html_content')
 * @param int $maxConcurrency Nombre maximum de requêtes concurrentes (par défaut: 10)
 * @param string $mode Mode de détection: 'complete' ou autre (par défaut: 'complete')
 * @param bool $force_redetect Force la redétection des informations en écrasant les informations dans Redis si disponible (par défaut: false)
 * @return array|null Résultat de l'API ou null en cas d'erreur
 * @throws DetectionApiBackpressureException Quand les retries 503 sont épuisés
 * @throws DetectionApiException Pour toute autre erreur (transport, 4xx, 5xx hors 503)
 */
function detectBatchUrls(array $items, int $maxConcurrency = 10, string $mode = 'complete', bool $force_redetect = false): ?array
```

- [ ] **Step 3: Replace the function body**

Use the Edit tool.

`old_string`:
```php
{
    // Nettoyer les données UTF-8 avant l'encodage JSON
    $items = sanitizeUtf8Recursive($items);

    // Préparer les données de la requête
    $data = [
        'items' => $items,
        'max_concurrency' => $maxConcurrency,
        'mode' => $mode,
        'force_refresh' => $force_redetect
    ];

    // Appel via call_api_hellopro avec timeout=0 (illimité)
    $result = call_api_hellopro('POST', 'detection_site_fr-service', '/api/v1/detect-batch', $data, false, 0);

    // call_api_hellopro retourne ['success' => false, ...] en cas d'erreur
    if (isset($result['success']) && $result['success'] === false) {
        throw new Exception("Erreur API detect-batch: " . ($result['message'] ?? 'Unknown error'));
    }

    return $result;
}
```

`new_string`:
```php
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

        // Happy path: wrapper returns decoded array (no 'success' key on 2xx)
        $isError = is_array($result) && isset($result['success']) && $result['success'] === false;
        if (!$isError) {
            return $result;
        }

        $httpCode = (int) ($result['http_code'] ?? 0);

        // 503 → retry honoring Retry-After > exponential backoff
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

        // Non-503 error (transport, 4xx, 5xx other) → no retry, throw typed
        throw new DetectionApiException(
            "detect-batch failed: HTTP {$httpCode}: " . ($result['message'] ?? 'unknown')
        );
    }

    throw new DetectionApiException("detect-batch retry loop exited without result");
}
```

- [ ] **Step 4: PHP syntax check**

```bash
php -l 'D:/DevHellopro/Marketplace/BO/admin/repertoire_test/moulinettes_interne/scrapping_produit_ia/fonctions/fonctions_scrapping.php'
```

Expected: `No syntax errors detected in <path>`.

- [ ] **Step 5: Sanity-lint the 5 untouched `detectBatchUrls()` callsite files**

```bash
php -l 'D:/DevHellopro/Marketplace/BO/admin/repertoire_test/moulinettes_rindra/script_divers/ponctuel/roadmap_v1/pct_traitement_crawling_rindra_BO.php'
php -l 'D:/DevHellopro/Marketplace/BO/admin/repertoire_test/moulinettes_interne/scrapping_produit_ia/script_identifier_site_fr_prospects_v2.php'
php -l 'D:/DevHellopro/Marketplace/BO/admin/repertoire_test/moulinettes_interne/scrapping_produit_ia/script_identifier_site_fr_v2.php'
php -l 'D:/DevHellopro/Marketplace/BO/admin/repertoire_test/moulinettes_interne/scrapping_produit_ia/script_find_variante_categorie_v2.php'
# fonctions_scrapping.php itself was linted in Step 4 — covers callsites at lines 8411 and 8503
```

Expected: all 4 commands return `No syntax errors detected`. (Signature is unchanged, so no callsite breaks; this step is a paranoia gate.)

- [ ] **Step 6: Stage and commit**

```bash
cd 'D:/DevHellopro/Marketplace'
git add 'BO/admin/repertoire_test/moulinettes_interne/scrapping_produit_ia/fonctions/fonctions_scrapping.php'
git diff --cached --stat
```

```bash
git commit -m "$(cat <<'EOF'
feat(detection): contrat caller dans detectBatchUrls (180s + retry 503)

Refonte de detectBatchUrls pour adopter le contrat caller
api-detection-langue-fr (spec 2026-04-27-...-bo-caller-contract).
Aligne le BO sur api-gateway (commit ba091eed) et crawler-service
(commit 238ab9d8) déjà conformes.

Changements:
- 4 constantes au-dessus de la fonction: DETECTION_REQUEST_TIMEOUT_S=180,
  DETECTION_CONNECT_TIMEOUT_S=10, DETECTION_MAX_RETRIES=2,
  DETECTION_BACKOFF_BASE_S=2
- require_once de DetectionApiException.php
- Boucle de retry HTTP 503 honorant Retry-After (précédence:
  header serveur > backoff exponentiel)
- Exceptions typées DetectionApiBackpressureException (503 épuisé)
  et DetectionApiException (autres). Hérite d'Exception donc les
  catch existants fonctionnent toujours
- error_log uniquement sur événements 503 et épuisement des retries
- Signature et type de retour préservés: les 5 callers existants ne
  changent pas

Corrige le bug timeout=0 (illimité) qui était silencieusement
contredit par le timeout 180s du gateway depuis ba091eed.
EOF
)"
git status
```

---

## Task 4: Migrate `script_launch_crawl_csv.php` Bypass Functions

**Goal:** Refactor `detectFrenchBatch()` and `detectFrenchSingle()` to delegate to `detectBatchUrls()`, eliminating the two callsites that bypass the caller contract.

**Files:**
- Modify: `D:\DevHellopro\Marketplace\BO\script\chatgpt\script_launch_crawl_csv.php` lines 221–264.
- IF Task 0 step 1 reported "no transitive include of `fonctions_scrapping.php`" → also add a `require_once` at the top of `script_launch_crawl_csv.php` for `fonctions_scrapping.php`.

**Acceptance Criteria:**
- [ ] `detectFrenchBatch()` delegates to `detectBatchUrls()` with `BATCH_SIZE` as max_concurrency, `'complete'` mode, no `force_redetect`.
- [ ] `detectFrenchSingle()` delegates to `detectBatchUrls([['url' => $url]], 1, 'complete', false)` and extracts `$response['results'][0]`.
- [ ] Both functions wrap calls in `try/catch` for `DetectionApiBackpressureException` and `DetectionApiException`, returning `[]` (batch) or `null` (single) on error.
- [ ] `error_log` lines added for both catch branches with the prefix `[script_launch_crawl_csv]`.
- [ ] If pre-flight Task 0 found no transitive include — `require_once` for `fonctions_scrapping.php` added near the top of the script.
- [ ] PHP syntax check passes.
- [ ] No callers of `detectFrenchBatch()` / `detectFrenchSingle()` need changes (return shapes preserved: `array` and `?array`).

**Verify:**
```bash
php -l 'D:/DevHellopro/Marketplace/BO/script/chatgpt/script_launch_crawl_csv.php'
```
→ `No syntax errors detected`.

**Steps:**

- [ ] **Step 1: (Conditional) Add `require_once` if Task 0 found no include chain**

If Task 0 step 1 found that `script_launch_crawl_csv.php` does NOT transitively include `fonctions_scrapping.php`, use the Edit tool to add the require near the existing `require_once`/`include` block at the top of the file. Match its style:

`old_string`: (the last existing require near the top — actual content captured during Task 0)

`new_string`: same line + a new line below:
```php
require_once __DIR__ . '/../../admin/repertoire_test/moulinettes_interne/scrapping_produit_ia/fonctions/fonctions_scrapping.php';
```

(Adjust the relative path based on the location of `script_launch_crawl_csv.php` — it lives at `BO/script/chatgpt/`, target lives at `BO/admin/repertoire_test/moulinettes_interne/scrapping_produit_ia/fonctions/`.)

If Task 0 found the include chain is already in place — skip this step.

- [ ] **Step 2: Replace `detectFrenchBatch()` body**

Use the Edit tool.

`old_string`:
```php
function detectFrenchBatch(array $urls): array
{
    $items = array_map(function($url) {
        return ['url' => $url];
    }, $urls);

    $response = call_api_hellopro('POST', API_SERVICE_DETECTION, '/api/v1/detect-batch', [
        'items' => $items,
        'mode' => 'complete',
        'max_concurrency' => BATCH_SIZE,
        'use_nlp_detection' => true,
    ]);

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

`new_string`:
```php
function detectFrenchBatch(array $urls): array
{
    $items = array_map(function($url) {
        return ['url' => $url];
    }, $urls);

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

- [ ] **Step 3: Replace `detectFrenchSingle()` body**

Use the Edit tool.

`old_string`:
```php
function detectFrenchSingle(string $url): ?array
{
    $response = call_api_hellopro('POST', API_SERVICE_DETECTION, '/api/v1/detect', [
        'url' => $url,
        'mode' => 'complete',
        'use_nlp_detection' => true,
    ]);

    if (isset($response['success']) && $response['success'] === false) {
        return null;
    }

    return $response;
}
```

`new_string`:
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

- [ ] **Step 4: PHP syntax check**

```bash
php -l 'D:/DevHellopro/Marketplace/BO/script/chatgpt/script_launch_crawl_csv.php'
```

Expected: `No syntax errors detected`.

- [ ] **Step 5: Find and lint downstream callers of the two refactored helpers (sanity)**

Use the Grep tool to locate callers within the same file:
```
pattern: detectFrenchBatch\(|detectFrenchSingle\(
glob: BO/script/chatgpt/script_launch_crawl_csv.php
output_mode: content
-n: true
```

Confirm callers consume the returns as `array` (batch) or `?array` (single) — both shapes preserved by this refactor.

- [ ] **Step 6: Stage and commit**

```bash
cd 'D:/DevHellopro/Marketplace'
git add 'BO/script/chatgpt/script_launch_crawl_csv.php'
git diff --cached --stat
```

```bash
git commit -m "$(cat <<'EOF'
refactor(script_launch_crawl_csv): déléguer détection FR à detectBatchUrls

Migre detectFrenchBatch et detectFrenchSingle pour utiliser le
wrapper central detectBatchUrls, supprimant les deux dernières
callsites BO qui bypassaient le contrat caller.

detectFrenchSingle envoie maintenant un batch d'un item à
/detect-batch (la endpoint /detect n'est plus appelée par le BO).

Les deux fonctions catch DetectionApiBackpressureException et
DetectionApiException, loggent via error_log avec préfixe
[script_launch_crawl_csv], et renvoient [] / null pour préserver
la résilience partielle des batchs (les callers existants
gèrent déjà les retours vides).

Préserve les signatures et types de retour, donc aucun caller
de detectFrenchBatch/Single ne change.
EOF
)"
git status
```

---

## Task 5: Add Smoke Verification Script

**Goal:** Provide a runnable CLI/browser script that exercises the contract paths for pre-merge regression checks and post-deploy smoke tests.

**Files:**
- Create: `D:\DevHellopro\Marketplace\BO\admin\repertoire_test\moulinettes_rindra\script_divers\ponctuel\pct_smoke_detection_contract_rindra_BO.php`

**Acceptance Criteria:**
- [ ] File exists at the exact path above.
- [ ] CLI/browser dual-mode bootstrap: `php_sapi_name() === 'cli'` branch sets nothing extra; non-CLI branch calls `set_time_limit(300)`, sets `Content-Type: text/plain`, and uses the auth gate path identified in Task 0 step 4.
- [ ] Loads `fonctions_scrapping.php` via `require_once` with path resolved relative to `__DIR__`.
- [ ] Test 1 (happy path): calls `detectBatchUrls([['url' => 'https://www.lemonde.fr']], 1, 'complete', false)` and asserts `!empty($result['results'][0]['ok'])`.
- [ ] Test 2 (503 backpressure): wraps a batch call in try/catch for `DetectionApiBackpressureException`; prints "skipped" if the exception is not raised (operator-coordinated).
- [ ] Test 3 (exception hierarchy): asserts `is_a('DetectionApiBackpressureException', 'DetectionApiException', true)` and `is_a('DetectionApiException', 'Exception', true)`.
- [ ] Test 4 (backward-compat): calls `call_api_hellopro('GET', 'detection_site_fr-service', '/api/v1/health', [], false, 30)` (no out-param, no connect timeout) and asserts `is_array($res)`.
- [ ] PHP syntax check passes.
- [ ] CLI run smoke-passes Tests 1, 3, 4 against staging detection service. Test 2 is operator-coordinated and may skip.

**Verify:**
```bash
php -l 'D:/DevHellopro/Marketplace/BO/admin/repertoire_test/moulinettes_rindra/script_divers/ponctuel/pct_smoke_detection_contract_rindra_BO.php'
```
→ `No syntax errors detected`. Then (optional, requires staging access):
```bash
cd 'D:/DevHellopro/Marketplace'
php BO/admin/repertoire_test/moulinettes_rindra/script_divers/ponctuel/pct_smoke_detection_contract_rindra_BO.php
```
Expected stdout includes lines `✓ Test 1 happy path`, `✓ Test 3 exception hierarchy`, `✓ Test 4 backward-compat signature`.

**Steps:**

- [ ] **Step 1: Resolve the auth gate path from Task 0 step 4**

Open `temp/preflight_detection_contract.md` (Task 0 output). Read the value under "Smoke script auth gate path (relative to its own location)". Substitute it into the file content below. If no auth gate is needed for ponctuel scripts in this directory, comment out the gate line in the file content with a leading `//`.

- [ ] **Step 2: Write the smoke script file**

Use the Write tool with `file_path = D:\DevHellopro\Marketplace\BO\admin\repertoire_test\moulinettes_rindra\script_divers\ponctuel\pct_smoke_detection_contract_rindra_BO.php` and content:

```php
<?php
/**
 * Smoke verification — api-detection-langue-fr caller contract.
 *
 * Vérifie le contrat caller adopté par detectBatchUrls() (spec
 * 2026-04-27-detection-langue-fr-bo-caller-contract-design.md).
 *
 * Usage:
 *   php pct_smoke_detection_contract_rindra_BO.php          (CLI, recommandé)
 *   https://bo.../pct_smoke_detection_contract_rindra_BO.php (navigateur)
 *
 * Test 2 (503 backpressure) nécessite une coordination ops:
 *   - Soit ADMISSION_MAX_SLOTS=0 temporairement sur api-detection-langue-fr
 *   - Soit DETECTION_FORCE_503=1 (debug branch, hors scope du commit)
 * Si non coordonné, Test 2 est skippé.
 */

$is_cli = (php_sapi_name() === 'cli');

if (!$is_cli) {
    set_time_limit(300);
    ini_set('max_execution_time', '300');
    header('Content-Type: text/plain; charset=utf-8');
    // Auth gate — substituer le chemin trouvé en Task 0 step 4
    // require_once __DIR__ . '/<auth_gate_path>';
}

require_once __DIR__ . '/../../../../moulinettes_interne/scrapping_produit_ia/fonctions/fonctions_scrapping.php';

// ─── Test 1 — happy path ─────────────────────────────────────────────────
$result = detectBatchUrls([['url' => 'https://www.lemonde.fr']], 1, 'complete', false);
assert(!empty($result['results'][0]['ok']), 'happy path should classify lemonde.fr as ok');
echo "✓ Test 1 happy path\n";

// ─── Test 2 — 503 backpressure (operator-coordinated) ────────────────────
try {
    detectBatchUrls([['url' => 'https://www.example.com']], 1, 'complete', false);
    echo "⚠ Test 2 skipped (server not saturated)\n";
} catch (DetectionApiBackpressureException $e) {
    echo "✓ Test 2 backpressure exception thrown: " . $e->getMessage() . "\n";
}

// ─── Test 3 — exception hierarchy ────────────────────────────────────────
assert(is_a('DetectionApiBackpressureException', 'DetectionApiException', true));
assert(is_a('DetectionApiException', 'Exception', true));
echo "✓ Test 3 exception hierarchy\n";

// ─── Test 4 — backward-compat call_api_hellopro signature ────────────────
$res = call_api_hellopro('GET', 'detection_site_fr-service', '/api/v1/health', [], false, 30);
assert(is_array($res));
echo "✓ Test 4 backward-compat signature\n";

echo "\nAll smoke checks passed.\n";
```

**Path verification note:** the `require_once` path is `__DIR__ . '/../../../../moulinettes_interne/scrapping_produit_ia/fonctions/fonctions_scrapping.php'`. Verify by walking the path from this file's directory:

- `__DIR__` = `BO/admin/repertoire_test/moulinettes_rindra/script_divers/ponctuel/`
- `/../../..` = `BO/admin/repertoire_test/moulinettes_rindra/`
- `/../../../../` = `BO/admin/repertoire_test/`
- `+ moulinettes_interne/scrapping_produit_ia/fonctions/` = `BO/admin/repertoire_test/moulinettes_interne/scrapping_produit_ia/fonctions/`

If the resolved path is wrong (e.g., file moved during plan execution), use `realpath()` once or count slashes carefully. The expected absolute path is `D:\DevHellopro\Marketplace\BO\admin\repertoire_test\moulinettes_interne\scrapping_produit_ia\fonctions\fonctions_scrapping.php`.

- [ ] **Step 3: PHP syntax check**

```bash
php -l 'D:/DevHellopro/Marketplace/BO/admin/repertoire_test/moulinettes_rindra/script_divers/ponctuel/pct_smoke_detection_contract_rindra_BO.php'
```

Expected: `No syntax errors detected`.

- [ ] **Step 4: (Optional) Run the smoke script if staging is reachable**

```bash
cd 'D:/DevHellopro/Marketplace'
php BO/admin/repertoire_test/moulinettes_rindra/script_divers/ponctuel/pct_smoke_detection_contract_rindra_BO.php
```

Expected stdout (Test 2 likely skipped in normal conditions):
```
✓ Test 1 happy path
⚠ Test 2 skipped (server not saturated)
✓ Test 3 exception hierarchy
✓ Test 4 backward-compat signature

All smoke checks passed.
```

If Test 1 fails because lemonde.fr is unreachable from the dev environment, replace the URL with a known-FR URL accessible from the BO staging perimeter and re-run.

If Test 4 returns a non-array on `/api/v1/health` (e.g., the gateway routes `health` as a static text response), adjust the assertion to `assert(!empty($res))` after confirming the actual response shape.

- [ ] **Step 5: Stage and commit**

```bash
cd 'D:/DevHellopro/Marketplace'
git add 'BO/admin/repertoire_test/moulinettes_rindra/script_divers/ponctuel/pct_smoke_detection_contract_rindra_BO.php'
git diff --cached --stat
```

```bash
git commit -m "$(cat <<'EOF'
chore(ponctuel): smoke script contrat caller detection-langue-fr

Ajoute pct_smoke_detection_contract_rindra_BO.php pour vérifier
le contrat caller post-déploiement et avant chaque merge tournant
les helpers detectBatchUrls.

Mode dual CLI/navigateur:
- CLI recommandé (Test 2 503 backpressure peut sleep ~30s+)
- Navigateur OK pour Tests 1/3/4 (set_time_limit 300s)

Tests:
1. Happy path — classifie lemonde.fr comme FR via /detect-batch
2. 503 backpressure — coordonné ops (ADMISSION_MAX_SLOTS=0) ou skip
3. Hierarchie d'exceptions — assertions is_a()
4. Backward-compat — call_api_hellopro avec signature historique
EOF
)"
git status
```

---

## Self-Review (Plan Author)

Already performed inline against the spec. Checklist:

| Spec section | Plan task | Coverage |
|---|---|---|
| Spec § Architectural Overview (3 layers) | Tasks 1, 2, 3, 4, 5 | All 5 file targets covered |
| Spec § 1 (Extended `call_api_hellopro`) | Task 2 | Code reproduced verbatim, + lint + commit + spot-check 3 baseline callers |
| Spec § 2 (Constants) | Task 3 step 2 | All 4 constants declared |
| Spec § 3 (Refactored `detectBatchUrls`) | Task 3 step 3 | Body reproduced verbatim |
| Spec § 4 (Exception hierarchy) | Task 1 | File reproduced verbatim |
| Spec § 5 (Migration of `script_launch_crawl_csv`) | Task 4 | Both functions covered + include-chain conditional |
| Spec § 6 (Smoke verification script) | Task 5 | File reproduced verbatim + verification step |
| Spec § Configuration Reference | Task 3 step 2 | Constants block carries the doc comments |
| Spec § Testing Strategy | Task 5 | CLI smoke + manual checklist (operator-coordinated 503 path noted) |
| Spec § Rollout (5 commits) | Tasks 1–5 | One commit per task, FR-only commit messages |
| Spec § Pre-flight verification (`use_nlp_detection`, include chain, auth gate) | Task 0 | All 3 unknowns resolved before code writes |
| Spec § Rollback strategy | Implicit | Each task is one commit, `git revert` per commit |
| Spec § Success Criteria | Task 5 verify step | Smoke script enforces happy-path + backward-compat asserts |

No placeholders. All code blocks reproduced with exact content. All file paths absolute. All commands runnable.

---

## Out-of-Scope Reminders (do NOT do as part of this plan)

- Cross-script concurrency cap (distributed limiter) — deferred per spec.
- Migration of BO to env-var config — deferred per spec.
- `/check-url` endpoint contract — no callers found.
- Refactoring non-detection callers of `call_api_hellopro` (crawler/comparator/etc.) — explicit non-goal.
- Adding PHPUnit / composer / CI test infra — explicit non-goal.

---

## Plan Metadata

- Spec: `docs/superpowers/specs/2026-04-27-detection-langue-fr-bo-caller-contract-design.md` (RAG-HP-PUB commit `97ff1555`)
- Companion spec: `docs/superpowers/specs/2026-04-20-detection-langue-fr-concurrency-defense-design.md`
- Target repo: `D:\DevHellopro\Marketplace`
- Target branch: `master`
- Commit language: FR-only
- Total commits expected: 5
- Approximate diff: ~80 lines added across BO; 1 line removed (the buggy `timeout=0` literal)
