# api-comparaison-texte — Contract Fix + Lean Hardening (Design)

- **Date:** 2026-06-21
- **Status:** Approved (design); pending implementation plan
- **Service:** `apps-microservices/api-comparaison-texte`
- **Cross-repo touch:** Hellopro BO (`BO/admin/repertoire_test/moulinettes_interne/scrapping_produit_ia/fonctions/fonctions_maj_crawling.php`) — the contract bug fix. **No gateway change.**
- **Author:** Tech Lead (brainstorm session)

---

## 1. Problem & diagnosis

### 1.1 Confirmed production bug — response-contract mismatch (HIGH)
The BO consumer reads response fields that the service does not emit, silently breaking title/description change-detection in the crawling-update flow.

- **Service emits** (`apps-microservices/api-comparaison-texte/app/models/schemas.py:103-109`): `ComparisonResult { url, similarity_ratio: float, decision: UPDATE|SKIP, reason, error? }`. There is **no `is_similar`, no `similarity`**.
- **BO reads** (`BO/.../fonctions_maj_crawling.php:1116-1117`):
  ```php
  $is_similar = $res['is_similar'] ?? true;   // key absent → ALWAYS true
  $similarity = $res['similarity'] ?? 1.0;    // key absent → ALWAYS 1.0
  ```
- **Effect:** `if (!$is_similar)` (`:1124`) is **never** true → titre/description are **never** marked modified via the API path. The `results`-empty fallback (`:1137`) doesn't fire either (the API returns results). Simple fields (prix/image/categorie/livraison/stock) still work via strict `==`. Net: title/description changes from crawling are not detected → stale products + missed Milvus re-ingest. Audit (`historique_comparaison_produit`) always records `similarity=1.0, is_similar=true`.

### 1.2 Service constraint (same shape as content-extractor)
- `app/api/routes.py:25,44` — `async def compare_single` / `compare_batch` run **synchronous** `compare_texts` (difflib `SequenceMatcher`, O(n·m)) + `extract_text_from_html` (BeautifulSoup/lxml) **inline in the coroutine** → block the event loop.
- `/compare-batch` is a **sequential `for` loop** (`routes.py:59`) over up to `BATCH_MAX_ITEMS` (500) items → one large batch occupies the loop for seconds; `/health` and other requests stall.
- `Dockerfile:11` — single uvicorn worker (no `--workers`). No Prometheus metrics, no admission control, no Redis.
- **Timeout exposure** is at the **PHP cURL** layer (the Go gateway has no downstream-timeout entry for `comparaison_texte-service` → `timeout=0`, no gateway 504). `comparaison_texte-service` is not in `ExcludedServices()` and not an nginx-sidecar route (nginx handles only `/crawler/`, `/migration/`, `/comparator/`=image), so it goes through the Go Gin proxy where `timeout=0` applies. Less acute than content-extractor's 30s symptom, but a runaway batch can still time out the caller and ties up a connection.

### 1.3 Consumer profile (drives scope — opposite of content-extractor)
The **only** consumer is BO crawling-update (`comparer_donnees_produit` → `comparer_textes_batch`), which calls `/compare-batch` **synchronously and blocks** on the result to make inline update decisions. **No crawler ×7**, no other consumer. A heavy consumer is hypothetical ("some day").

---

## 2. Decisions (locked in brainstorm)

| # | Decision | Choice |
|---|---|---|
| D1 | Where to fix the contract bug | **BO consumer** reads the real contract (`decision`/`similarity_ratio`); service unchanged |
| D2 | Scope | **Lean hardening** — axis-1 (offload + workers) + metrics + optional admission. **No async-job, no Redis (cache or job store).** |
| D3 | Bug fix sequencing | **Task 1 of the plan** (ships first, highest priority) |

**Rationale for "no async / no Redis" (YAGNI, critically assessed):** the sole consumer blocks on results (async submit→poll adds latency for zero benefit). A result cache *could* hit on products unchanged across crawl cycles (identical `old_text`/`new_content`), but each difflib call is cheap (text-only input, no multi-page header/footer extraction), so the saved compute does not justify a Redis dependency — defer until profiling shows compare-time dominates. Both are deferred until a real heavy consumer exists.

---

## 3. Contract fix (BO — Task 1)

`BO/.../fonctions_maj_crawling.php:1116-1117` becomes:
```php
$is_similar = (($res['decision'] ?? 'UPDATE') === 'SKIP');
$similarity = $res['similarity_ratio'] ?? 1.0;
```
- **Semantics:** `SKIP` = similar enough → no update; `UPDATE` → modified. Missing `decision` or a per-item error (service returns `decision=UPDATE, reason="error"` for failed items, `routes.py:71-77`) → defaults to `'UPDATE'` → treated as **modified** (fail-safe: assume changed on malformed/error response, vs the old code's unsafe "assume similar/skip").
- Everything else in `comparer_donnees_produit` (`fonctions_maj_crawling.php:1028-1160`) is unchanged: the `!empty($result_comparaison['results'])` guard (`:1112`), the `_champ` index mapping, `comparaison_details` audit, and the strict-`==` fallback (`:1137-1153`).
- `BO/` is tracked in git → normal Hellopro commit (NOT the Ecritel-FTP `site/` workflow).
- The wrapper `comparer_textes_batch` (`:990-998`) is unchanged (it already posts to `comparaison_texte-service /api/v1/compare-batch` with `{items, threshold}`).

---

## 4. Service architecture — axis-1 (offload + workers)

- Keep the pure compute as-is: `app/core/text_comparator.compare_texts` (sync) + `app/services/html_cleaner.extract_text_from_html` (sync). No algorithm change.
- **Offload off the event loop:**
  - `/compare`: `result = await asyncio.to_thread(_compare_one, request)` where `_compare_one` does the HTML-clean + `compare_texts` synchronously and returns the `ComparisonResult` fields.
  - `/compare-batch`: offload the **entire batch loop as one unit** → `results, error_count = await asyncio.to_thread(_run_batch, request.items, request.threshold)`. The loop body is the current sequential logic (per-item try/except preserved).
- **GIL honesty (load-bearing rationale):** `difflib.SequenceMatcher` is pure-Python (GIL-bound). `extract_text_from_html` uses `BeautifulSoup(html, "lxml")` whose *parse* step is C (libxml2, releases the GIL partially) — but **the sole production consumer sends `content_type=text`** (`fonctions_maj_crawling.php:1087`), so `extract_text_from_html` is **never on the hot path** and the offloaded work is **difflib only → unambiguously GIL-bound**. Therefore per-item `asyncio.gather` + `to_thread` would add thread-pool churn for **no CPU speedup**. Whole-batch offload keeps the event loop responsive (health checks, concurrent requests) at the batch's natural sequential speed. **Cross-batch parallelism comes from `UVICORN_WORKERS` × replicas (processes), not threads.** A genuine single-batch speedup would require `ProcessPoolExecutor` (rejected — pickling large text pairs) or swapping difflib→rapidfuzz (C-backed, GIL-releasing, but a different similarity algorithm that shifts scores and would require re-tuning the 0.85 threshold — out of scope, noted for a future heavy consumer).
- **Batch shape — note vs the content-extractor template:** content-extractor's `run_batch` uses **per-item `asyncio.gather`** under a semaphore; this service deliberately uses a **single whole-batch `to_thread`** (per the GIL rationale above). Reuse the `to_thread` *idiom* from content-extractor, **not** its per-item gather shape.
- `Dockerfile` CMD → `["sh","-c","uvicorn main:app --host 0.0.0.0 --port 8998 --proxy-headers --workers ${UVICORN_WORKERS:-2}"]`.

---

## 5. Admission (optional, off by default)

`app/core/admission.py` — `SyncAdmission(max_inflight)` with `try_acquire()` (atomic check+increment, no await between) / `release()` (idempotent floor-0), mirroring content-extractor. Both endpoints: on `try_acquire()` False → `503` + `Retry-After: ADMISSION_RETRY_AFTER_S`. Gated by `SYNC_MAX_INFLIGHT` (default `0` = disabled → always admit, zero behaviour change).

---

## 6. Metrics (new — service currently has none)

`app/core/metrics.py` using `prometheus-client` directly (standalone — no shared libs), exposed at `GET /metrics` via `generate_latest()` (the `api-detection-langue-fr` pattern, not a WSGI mount):
- `comparison_requests_total{endpoint,status}` (Counter)
- `comparison_request_duration_seconds{endpoint}` (Histogram)
- `comparison_decision_total{decision}` (Counter — `UPDATE`/`SKIP`; this signal would have surfaced the §1.1 bug: high SKIP rate vs zero downstream updates)
- `comparison_batch_size` (Histogram)
- `comparison_sync_admission_rejected_total` (Counter; only meaningful when admission enabled)

If `/metrics` must be scrapeable unauthenticated, expose it as a `public_path` via the **account-service-frontend catalog** (the Go gateway `api-gateway-go` is catalog-driven — there is no hardcoded path list). Operator concern, deferred.

---

## 7. Configuration

`app/core/config.py` (pydantic `BaseSettings`) adds:

| Var | Default | Purpose |
|---|---|---|
| `UVICORN_WORKERS` | `2` | worker processes per replica (CPU parallelism lever) |
| `SYNC_MAX_INFLIGHT` | `0` | sync admission cap (`0` = disabled) |
| `ADMISSION_RETRY_AFTER_S` | `15` | `Retry-After` value on admission 503 |

Unchanged: `APP_NAME`, `APP_VERSION`, `DEBUG`, `SIMILARITY_THRESHOLD` (0.85), `BATCH_MAX_ITEMS` (500).

---

## 8. Capacity — "heavy use" answer

CPU/GIL-bound. Sustained throughput ≈ `cores / p` where `cores = UVICORN_WORKERS × replicas`, `p` = avg compare seconds (calibrate from the new `comparison_request_duration_seconds` histogram). **No cache** (low ROI here). For a future heavy consumer: scale processes/replicas first; if single-batch latency becomes the bottleneck, then evaluate rapidfuzz or an async-job API (both deferred). Admission sheds overload as `503` rather than degrading into timeouts.

---

## 9. Error handling & resilience

- Per-item batch errors already captured (`decision=UPDATE, similarity_ratio=0.0, reason="error", error=str(e)`, `routes.py:71-77`) — preserved inside the offloaded `_run_batch`.
- Admission 503 raised before any work.
- Metrics recorded on 200 / 500 / 503 paths.
- `BATCH_MAX_ITEMS` 400-guard unchanged (`routes.py:49-53`).

---

## 10. Files touched

**RAG-HP-PUB (`features/poc`):**
- `apps-microservices/api-comparaison-texte/app/api/routes.py` — offload handlers; record metrics + admission.
- `apps-microservices/api-comparaison-texte/app/core/config.py` — new settings.
- **new** `apps-microservices/api-comparaison-texte/app/core/metrics.py`, `app/core/admission.py`.
- `apps-microservices/api-comparaison-texte/main.py` — add `/metrics` endpoint.
- `apps-microservices/api-comparaison-texte/Dockerfile` — `--workers` only. (This Dockerfile currently runs as **root** with **no HEALTHCHECK**, unlike the content-extractor template; non-root `USER` + HEALTHCHECK are a `docker-security.md` gap **deferred out of the lean scope** — note as a follow-up, not done here.)
- `apps-microservices/api-comparaison-texte/requirements.txt` — `prometheus-client`.
- `apps-microservices/api-comparaison-texte/tests/*` — new tests.

**Hellopro:**
- `BO/admin/repertoire_test/moulinettes_interne/scrapping_produit_ia/fonctions/fonctions_maj_crawling.php` — 2-line contract fix (Task 1).

**No gateway change** (`comparaison_texte-service` stays unlisted → `timeout=0` at the Go gateway). Optional deferred item: add a `comparaison_texte-service` entry to `api-gateway-go/internal/config/service_map.go` `BuildDownstreamTimeouts()` if a heavy consumer makes the unbounded gateway timeout a concern.

---

## 11. Testing strategy

Per-component pytest (test stem must match the production file for the `tdd-gate` hook):
- `tests/test_text_comparator.py` (exists) — stays green (algorithm unchanged).
- `tests/test_api.py` (exists) — stays green; extend: a slow-compare offload-non-block assertion; admission 503 when `SYNC_MAX_INFLIGHT` exceeded; `/metrics` returns 200 + exposition text.
- `tests/test_admission.py` (new) — `SyncAdmission` disabled/cap/release/floor.
- `tests/test_metrics.py` (new) — metric objects are the right Prometheus types.
- BO: PHP — no unit harness; verify in prod (title/desc detection fires; `comparison_decision_total{decision="UPDATE"}` climbs). Optionally a short `.md` note alongside the BO change.

Constraint: run targeted test files; if pytest collection fails with `SystemError`, re-pin `pydantic-core==2.46.4`. The global env may lack this service's deps (`beautifulsoup4`, `lxml`, `prometheus-client`) — install the specific missing dep, never `pip install -r requirements.txt`.

---

## 12. Rollout (single phase, all flag-safe)

1. Ship the **BO contract fix** (Task 1) — immediate prod value (title/desc detection restored); falls back to strict `==` if the API is ever down.
2. Deploy the service (workers + offload + metrics; `SYNC_MAX_INFLIGHT=0`). Nothing to gate (no Redis, no async). Scrape `/metrics`; watch `comparison_decision_total` to confirm the fix end-to-end (UPDATE rate becomes non-zero).

---

## 13. Risks / open items

1. **GIL** → a single large batch is not faster; throughput scales with processes/replicas. Documented so operators don't expect intra-batch speedup.
2. **BO fix default change** — malformed/error responses now default to "modified" (safer) rather than "similar". Intentional. **Cost:** a transient per-item service error now forces an update + Milvus re-ingest for that one product (vs the old code's silent skip). Acceptable — errors are rare and re-ingest is idempotent; failing toward data-freshness is the right default.
3. **Deferred (for a real heavy consumer):** rapidfuzz (faster, GIL-releasing — needs threshold re-tuning), async submit→poll + Redis, Go-gateway downstream-timeout entry.
4. `/metrics` auth exposure — confirm the gateway public-path policy if unauthenticated scraping is desired.

---

## Appendix A — Reuse map (this session's content-extractor templates)

| Need | Source |
|---|---|
| `asyncio.to_thread` offload pattern | `apps-microservices/content-extractor-api-service/app/core/extractor_service.py` |
| `SyncAdmission` guard | `apps-microservices/content-extractor-api-service/app/core/admission.py` |
| Standalone Prometheus `/metrics` (`generate_latest`) | `apps-microservices/api-detection-langue-fr/main.py` + `app/core/metrics.py` |
| Multi-worker Dockerfile CMD | `apps-microservices/content-extractor-api-service/Dockerfile` |

**NOT reused (deliberately):** result cache, async job store/manager, Redis `cache_service` — out of scope per D2.
