# Crawler Timing Instrumentation — Design

**Date:** 2026-04-30
**Status:** Approved (pending implementation)
**Scope:** `apps-microservices/crawler-service/crawler/`
**Goal:** One-run instrumentation to identify the dominant latency cost in a crawl, so the tuning effort that follows is evidence-based rather than speculative.

## Problem

Operators report the crawler "feels slow" but no measurement exists to confirm or locate the bottleneck. Several plausible suspects compete:

- **Browser:** Camoufox stealth Firefox is slower than headless Chromium under typical loads.
- **Detection API:** every page handler awaits a `/detect` call gated by `pLimit(DETECTION_MAX_CONCURRENCY=5)`. Saturation is invisible.
- **Apify proxy:** adds round-trip latency on every request.
- **Crawlee autoscaler:** `availableMemoryRatio: 0.8` may throttle concurrency aggressively under heavy heap usage.
- **Rate cap:** `maxRequestsPerMinute=100` (default `perminute=100` job arg) is a hard ceiling well below network capacity for fast sites.

Tuning the wrong knob (e.g., raising concurrency when the bottleneck is API queue depth) wastes effort and may degrade other metrics. The goal of this spec is to add temporary, env-gated instrumentation that produces enough evidence to pick the right knob.

## Architecture

Two layers of measurement, both written to a per-crawl JSONL file plus an end-of-run summary:

1. **Per-page timeline** — Crawlee `preNavigationHooks` and `postNavigationHooks` plus inline timestamps inside the route handler capture each phase of one page's lifecycle.
2. **Pool-level samples** — a single `setInterval` sampler reads Crawlee's autoscaled pool stats and the detection client's `pLimit` instance every 5 seconds.

A new `TimingRecorder` class owns both the JSONL stream and the in-memory accumulator that emits the summary at crawl end.

The instrumentation is enabled when `TIMING_ENABLED=true` in the environment. When disabled, the hooks are not registered and the recorder is not constructed — zero overhead in normal production runs.

## Components

### `crawler/src/class/TimingRecorder.ts` (new file)

- Constructor: `(crawlId: string, outputDir: string)`. Opens append stream at `outputDir/timing.jsonl`.
- `recordPage(entry: PageTimingEntry): void` — write one JSONL line, accumulate phase durations into per-phase histograms (median, p95, p99 via reservoir or simple sorted-array since N is bounded by site size).
- `recordPoolSample(entry: PoolSample): void` — append to in-memory list of samples.
- `finalize(): Promise<void>` — flush stream, compute summary, write `outputDir/timing-summary.json`, log a one-page console summary.

### Page timing instrumentation

In the same file where `PlaywrightCrawler` is constructed (`crawler/src/functions.ts` near line 525):

- `preNavigationHooks: [(crawlingContext) => { crawlingContext.userData._timing = { dequeueAt: Date.now() }; }]` — record when handler begins.
- Within the existing route handler in `crawler/src/routes.ts`, capture timestamps before/after the `detectionClient.detect(...)` call and before returning.
- `postNavigationHooks: [(crawlingContext) => { crawlingContext.userData._timing.postNavAt = Date.now(); }]` — record navigation completion.
- At handler return, build a `PageTimingEntry` and call `recorder.recordPage(entry)`.

Entry shape:

```typescript
interface PageTimingEntry {
    url: string;
    t: number;             // dequeue timestamp (ms since epoch)
    wait_ms: number;       // dequeue → preNav (autoscaler queue time)
    nav_ms: number;        // preNav → postNav
    pre_detect_ms: number; // postNav → detect.start
    detect_ms: number;     // detect.start → detect.end
    post_ms: number;       // detect.end → handler return
    total_ms: number;      // dequeue → handler return
    detect_method?: string; // for context (langHtml, direct_match, etc.)
    detect_ok?: boolean;
}
```

### Pool-level instrumentation

A single sampler `setInterval(() => { ... }, 5000)` started after Crawlee init and stopped on `crawler.run()` completion (registered in the same place that constructs the recorder).

Sample shape:

```typescript
interface PoolSample {
    t: number;
    crawlee: {
        currentConcurrency: number;
        desiredConcurrency: number;
        maxConcurrency: number;
    };
    detect: {
        pendingCount: number;
        activeCount: number;
    };
    memory: {
        used_mb: number;
        budget_mb: number;
        ratio: number;
    };
    rolling: {
        pages_per_min: number;
    };
}
```

`crawler.autoscaledPool` and the `pLimit` instance both expose the relevant counters as properties — no monkey-patching required.

### Summary report

End-of-run summary emits to stdout AND to `outputDir/timing-summary.json`:

```json
{
    "crawl_id": "6066",
    "duration_s": 482,
    "pages_total": 156,
    "pages_per_min_avg": 19.4,
    "pages_per_min_max_sustained": 28.1,
    "phases": {
        "wait_ms":       { "median": 12,    "p95": 80,    "p99": 240,   "share_of_total_pct": 0.5 },
        "nav_ms":        { "median": 3400,  "p95": 8200,  "p99": 14000, "share_of_total_pct": 62.0 },
        "pre_detect_ms": { "median": 5,     "p95": 15,    "p99": 40,    "share_of_total_pct": 0.1 },
        "detect_ms":     { "median": 1200,  "p95": 4500,  "p99": 9000,  "share_of_total_pct": 28.0 },
        "post_ms":       { "median": 50,    "p95": 200,   "p99": 800,   "share_of_total_pct": 9.4 }
    },
    "pool": {
        "crawlee_avg_concurrency": 3.2,
        "crawlee_max_concurrency_reached": 5,
        "crawlee_throttle_pct": 14.7,
        "detect_avg_active": 4.1,
        "detect_avg_pending": 11.3,
        "detect_saturated_pct": 41.0
    }
}
```

`detect_saturated_pct` = % of pool samples where `activeCount === DETECTION_MAX_CONCURRENCY` AND `pendingCount > 0`.
`crawlee_throttle_pct` = % of pool samples where `currentConcurrency < desiredConcurrency`.

### Console summary

A single block printed at crawl end:

```
=== Timing summary ===
Pages: 156 in 482s (avg 19.4 pages/min, max 28.1 sustained)
Phase share of total handler time:
  nav_ms        62.0%  (median 3400ms, p95 8200ms)
  detect_ms     28.0%  (median 1200ms, p95 4500ms)
  post_ms        9.4%  (median 50ms,   p95 200ms)
Pool:
  Crawlee avg concurrency: 3.2 / max reached: 5 / throttled 14.7% of time
  Detect API saturated 41.0% of time (pending queue non-empty at concurrency cap)
```

This single block tells the operator which knob to tune.

## Data flow

```
preNavigationHook  → userData._timing = { dequeueAt }
   ↓
Playwright navigation (Camoufox)
   ↓
postNavigationHook → userData._timing.postNavAt
   ↓
route handler (routes.ts)
   - userData._timing.detectStartAt = Date.now()
   - await detectionClient.detect(...)
   - userData._timing.detectEndAt = Date.now()
   - ... (link enqueue, etc.)
   - recorder.recordPage(buildEntry(crawlingContext))
   ↓
sampler setInterval (every 5s, parallel)
   - recorder.recordPoolSample(...)
   ↓
crawler.run() returns
   ↓
recorder.finalize() → JSONL flush + summary write + console block
```

## Configuration

- `TIMING_ENABLED=true` — opt-in, default off. When false, no hooks registered, no sampler started, no recorder constructed.
- `TIMING_SAMPLE_INTERVAL_MS=5000` — pool sampler interval. Override only for very short test crawls.
- `TIMING_SUMMARY_FLUSH_MS=30000` — periodic in-process summary flush interval. Each tick rebuilds the summary from accumulators and overwrites `timing-summary.json` so a crash leaves the latest snapshot on disk.
- Output directory: `storage/{crawl_id}/` (already a per-crawl directory).

## Durability and crash resilience

The crawler can crash mid-run (OOM, force-stop, container kill). Timing data must survive partial runs, otherwise the instrumentation is worthless on the very runs that need investigation.

**JSONL stream.** `fs.createWriteStream(path, { flags: 'a' })` with explicit `stream.write(line + '\n')` per `recordPage` call. Stream is flushed (`stream.cork`/`uncork` not used; default behavior writes immediately to the kernel buffer). For per-line OS durability under crash, the recorder calls `fs.fsyncSync(fd)` once per N lines (N=50, configurable via `TIMING_FSYNC_EVERY_N`). Exit handlers (`process.on('beforeExit')`, `process.on('SIGTERM')`, `process.on('SIGINT')`) call `recorder.finalize()` to flush remaining bytes and write the final summary.

**Summary file.**
- Written periodically every `TIMING_SUMMARY_FLUSH_MS` (default 30s) by an in-process timer. Each tick rebuilds the summary from current accumulators and atomically overwrites `timing-summary.json` (write to `.tmp` then `rename`).
- Written one final time at `finalize()`.
- Reconstructible post-hoc from the JSONL via a small standalone tool (next subsection) when the in-process summary is missing or corrupt.

**Post-hoc reconstruction tool.** A standalone Node script at `apps-microservices/crawler-service/crawler/src/tools/timing-summary.ts` reads any `timing.jsonl` and emits the same `timing-summary.json` shape. Invocation: `npx tsx src/tools/timing-summary.ts /path/to/timing.jsonl`. The script reuses the same aggregator logic as `TimingRecorder.finalize()` (extract aggregator into a shared module so both the in-process recorder and the post-hoc tool consume it identically).

**Auto-regeneration on Node.js startup.** When `TIMING_ENABLED=true` and the recorder constructor finds an existing `timing.jsonl` for a crawl that is being resumed (e.g., update mode, OOM relaunch), it offers two policies:
- `TIMING_RESUME_POLICY=replay` (default) — read the existing JSONL into the aggregator before opening for append. The summary picks up where the previous run left off.
- `TIMING_RESUME_POLICY=overwrite` — truncate the JSONL and start fresh.

For the first iteration, default to `replay`. The behavior is documented in the JSDoc on the recorder constructor.

## Local retention after archive cleanup

`apps-microservices/crawler-service/app/core/crawler_manager.py` line 1690 maintains the `files_to_keep` whitelist used by `_cleanup_local_data()` after a successful archive. Both timing files are added to that set:

```python
files_to_keep = {'crawler.log', '_callback_payload.json',
                 '_completion_marker.json', '_status_snapshot.json',
                 '_exit_reason.json', '_update_report.json',
                 'update_stats.json',
                 'timing.jsonl', 'timing-summary.json'}
```

The .tar.gz archive already contains both files (it is built from the full storage directory before cleanup); the keep-list change preserves them on local disk too, so an operator can `cat` or `jq` them without unpacking the archive.

## Testing

- Unit tests for `TimingRecorder`:
  - JSONL line per call to `recordPage`.
  - Aggregate summary computes correct median/p95/p99 from a known input set.
  - `detect_saturated_pct` and `crawlee_throttle_pct` math.
  - Periodic summary flush rewrites the file at the configured interval (use a fake clock).
  - `replay` resume policy reads an existing JSONL into the aggregator before further appends.
- Unit tests for the post-hoc `timing-summary.ts` tool:
  - Given a known JSONL fixture, output equals the in-process aggregator's output for the same input.
  - Handles empty JSONL (zero pages) without crashing.
- Integration: a 10-page test crawl with `TIMING_ENABLED=true` produces one `timing.jsonl` and one `timing-summary.json`. Assert files exist, JSONL has 10 lines, summary has all expected keys.
- Crash-resilience integration: kill the crawler mid-run (SIGKILL the worker after ~5 pages). Verify `timing.jsonl` contains the partial trace. Run the post-hoc tool against it and assert the regenerated `timing-summary.json` is well-formed and reflects the partial pages.
- Negative: with `TIMING_ENABLED=false`, no files are produced and crawl behavior is unchanged.

## Out of scope

- **Optimization.** This spec only adds measurement. Tuning decisions belong to a follow-up spec written after one crawl produces evidence.
- **Permanent observability.** No OpenTelemetry, Prometheus, or Grafana wiring. JSONL + console block is sufficient for one-shot diagnosis.
- **Per-task heatmap or HTML dashboard.** JSONL is consumable by `jq`, `awk`, or a quick Python notebook if a visual is needed.
- **Histogram buckets that survive across crawl IDs.** Each crawl produces its own files; aggregation across crawls is a future concern.
- **Sampling reduction for very large crawls.** Recorder writes one line per page handled; for 100k-page crawls the file is ~30MB plain text — tolerable. Compression or sampling can be added later if needed.
- **Replacing the existing memory watchdog.** The watchdog at `main.ts:233-380` keeps doing what it does; the recorder reads memory data from the same source but does not interfere.

## Acceptance criteria

- A test run with `TIMING_ENABLED=true` produces `storage/{id}/timing.jsonl` and `storage/{id}/timing-summary.json`.
- A test run with `TIMING_ENABLED=false` produces neither file and crawl behavior is byte-identical to current behavior.
- Console summary block prints at crawl end and identifies the dominant phase by percentage.
- Per-phase median/p95/p99 are mathematically correct (verified by unit tests).
- Pool sampler captures both Crawlee autoscaler state and detect-API queue state simultaneously.
- `timing.jsonl` and `timing-summary.json` survive `_cleanup_local_data()` (added to `files_to_keep` in `crawler_manager.py`).
- A SIGKILL mid-run leaves a partial `timing.jsonl` whose contents the post-hoc `timing-summary.ts` tool can convert to a well-formed summary.
- The periodic summary flush (default 30s) overwrites `timing-summary.json` so a crash leaves a recent in-process snapshot on disk.
- All existing crawler tests still pass.
- `npm run build` clean.
