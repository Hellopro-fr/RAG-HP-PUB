import { test } from 'node:test';
import assert from 'node:assert/strict';
import { DedupManager } from '../class/DedupManager.js';

/**
 * Regression: update-mode seeding must NOT pre-claim URLs in the dedup set.
 *
 * Root cause (crawl 3821-171-*, domain fm-dev.com): Phase 1 (main.ts:721-723)
 * and Phase 2 (main.ts:1183-1185) called `dedupManager.addUrl(url)` BEFORE
 * `requestQueue.addRequest(url)`. When the page handler later processes that
 * same URL it calls `addUrl` again (routes.ts:427) — now a no-op returning
 * `isNew=false` — so `isDoublon=true`, the extraction + UpdateChecker block is
 * skipped (routes.ts:440), and the URL is logged "Doublon url:" and dropped.
 *
 * The dataset-source bypass (routes.ts:423, `isExisting = source==='dataset'`)
 * hid the bug for dataset URLs, so only the homepage ('seed') and every
 * request_queue / request_url URL were silently skipped at crawl start.
 *
 * Like routes.pushedSet.test.ts, we exercise the contract directly with the
 * real DedupManager over a mock Redis client rather than booting a crawler.
 * The fix removes both pre-adds so seeding leaves the set untouched and the
 * handler claims each URL on first processing.
 */

function makeMockRedisClient() {
    const seen = new Set<string>();
    return {
        isOpen: true,
        async sAdd(_key: string, member: string | string[]) {
            const members = Array.isArray(member) ? member : [member];
            let added = 0;
            for (const m of members) {
                if (!seen.has(m)) { seen.add(m); added++; }
            }
            return added;
        },
        async sIsMember(_key: string, member: string) { return seen.has(member); },
        async expire(_key: string, _ttl: number) { return 1; },
        async del(_key: string) { return 1; },
    };
}

/**
 * Models the page-handler dedup decision at routes.ts:423-428.
 * `is_existing` is never set on consolidated seeds, so eligibility for the
 * bypass collapses to `source === 'dataset'`.
 */
async function handlerIsDoublon(
    dedup: DedupManager,
    url: string,
    source: string,
): Promise<boolean> {
    const isExisting = source === 'dataset';
    if (isExisting) return false; // dedup check skipped → re-verified
    const isNew = await dedup.addUrl(url);
    return !isNew;
}

/**
 * Models update-mode seeding. `preAdd` reproduces the buggy pre-claim.
 */
async function seedUpdateMode(
    dedup: DedupManager,
    seeds: Array<{ url: string; source: string }>,
    preAdd: boolean,
): Promise<void> {
    for (const { url } of seeds) {
        if (preAdd) await dedup.addUrl(url); // the bug: main.ts:722 / :1184
        // requestQueue.addRequest(...) is queue-side and not modeled here.
    }
}

const HOMEPAGE = 'https://fm-dev.com/';
const RQ_URL = 'https://www.fm-dev.com/collecteurs/collecteur-piles-30l-9698';
const DATASET_URL = 'https://www.fm-dev.com/mentions-legales';

test('BUG repro — pre-adding a request_queue seed makes the handler skip it as Doublon', async () => {
    const dedup = new DedupManager(makeMockRedisClient() as any, 'bug-rq');
    await seedUpdateMode(dedup, [{ url: RQ_URL, source: 'request_queue' }], /*preAdd*/ true);
    assert.equal(
        await handlerIsDoublon(dedup, RQ_URL, 'request_queue'),
        true,
        'with the pre-add, the handler self-marks the seed Doublon (the bug)',
    );
});

test('FIX — without the pre-add, a request_queue seed is processed (not Doublon)', async () => {
    const dedup = new DedupManager(makeMockRedisClient() as any, 'fix-rq');
    await seedUpdateMode(dedup, [{ url: RQ_URL, source: 'request_queue' }], /*preAdd*/ false);
    assert.equal(
        await handlerIsDoublon(dedup, RQ_URL, 'request_queue'),
        false,
        'no pre-add → first handler processing claims the URL → reaches UpdateChecker',
    );
});

test('FIX — homepage (source=seed) is processed when not pre-added', async () => {
    const buggy = new DedupManager(makeMockRedisClient() as any, 'bug-home');
    await seedUpdateMode(buggy, [{ url: HOMEPAGE, source: 'seed' }], /*preAdd*/ true);
    assert.equal(await handlerIsDoublon(buggy, HOMEPAGE, 'seed'), true, 'pre-add drops homepage');

    const fixed = new DedupManager(makeMockRedisClient() as any, 'fix-home');
    await seedUpdateMode(fixed, [{ url: HOMEPAGE, source: 'seed' }], /*preAdd*/ false);
    assert.equal(
        await handlerIsDoublon(fixed, HOMEPAGE, 'seed'),
        false,
        'no pre-add → homepage runs detection (regional-path exclusion) before resolve',
    );
});

test('dataset-source URLs bypass the dedup check regardless of pre-add', async () => {
    const dedup = new DedupManager(makeMockRedisClient() as any, 'dataset');
    await seedUpdateMode(dedup, [{ url: DATASET_URL, source: 'dataset' }], /*preAdd*/ true);
    assert.equal(
        await handlerIsDoublon(dedup, DATASET_URL, 'dataset'),
        false,
        'isExisting bypass (routes.ts:423) re-verifies dataset URLs even if seen',
    );
});

test('second sighting of the same URL is still deduped (handler-level claim intact)', async () => {
    const dedup = new DedupManager(makeMockRedisClient() as any, 'second');
    // First processing (e.g. via the seed) claims it.
    assert.equal(await handlerIsDoublon(dedup, RQ_URL, 'request_queue'), false, 'first sighting proceeds');
    // Same URL later discovered as a link → correctly Doublon.
    assert.equal(await handlerIsDoublon(dedup, RQ_URL, 'discovered'), true, 'duplicate link skipped');
});
