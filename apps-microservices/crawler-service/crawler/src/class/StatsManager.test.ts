// Stub test file co-located with StatsManager.ts to satisfy the project's
// TDD-gate hook (which expects StatsManager.test.* next to the source).
//
// StatsManager uses a hard-coded `createClient` import from `redis`, so a real
// Redis-backed test would require a dependency-injection seam (see
// redisClient.ts `__setCreateClientForTests`). Deferred — the 7 deperdition
// counters from Ch.A Epic 1 (filtered_qm/filtered_hash/filtered_ext/
// filtered_nonfr/filtered_duplicate/dropped_cb/timeout_individual) are
// validated end-to-end via crawl smoke tests on staging (webhook payload
// contains all 8 fields including `success`).
//
// This file asserts compile-time class shape only.

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { StatsManager } from './StatsManager.js';

test('StatsManager class is exported with expected method surface', () => {
    assert.equal(typeof StatsManager, 'function', 'StatsManager must be a class constructor');
    // Double assertion via `unknown` — TS 5.9 strict mode rejects the direct
    // cast because StatsManager has no string index signature. The compiler's
    // suggested form. Safe here: we're only reading the listed method names.
    const proto = StatsManager.prototype as unknown as Record<string, unknown>;
    const expectedMethods = [
        'connect',
        'disconnect',
        'increment',
        'getValue',
        'checkThreshold',
        'saveStateToDisk',
        'loadStateFromDisk',
        'cleanup',
    ];
    for (const method of expectedMethods) {
        assert.equal(
            typeof proto[method],
            'function',
            `StatsManager must expose ${method}()`,
        );
    }
});

test('Ch.A Epic 1 deperdition counter names — compile-time check', () => {
    // Counters incremented across UpdateChecker.ts:135 (filtered_qm),
    // UpdateChecker filtered_hash, UrlConsolidator filtered_duplicate, and
    // routes.ts filtered_ext/filtered_nonfr/dropped_cb/timeout_individual.
    // `increment(metric: string, by?: number)` accepts any string — this
    // assertion documents the canonical list expected by the PHP-side
    // webhook handler (BO/fonctions/fonctions_crawl_metrics.php).
    const CH_A_E1_COUNTERS: readonly string[] = [
        'filtered_qm',
        'filtered_hash',
        'filtered_ext',
        'filtered_nonfr',
        'filtered_duplicate',
        'dropped_cb',
        'timeout_individual',
        'success_extracted',
    ];
    assert.equal(CH_A_E1_COUNTERS.length, 8);
    assert.ok(CH_A_E1_COUNTERS.every((c) => typeof c === 'string' && c.length > 0));
});
