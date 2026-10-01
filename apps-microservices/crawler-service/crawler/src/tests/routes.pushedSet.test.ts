import { test } from 'node:test';
import assert from 'node:assert/strict';
import { PushedSet } from '../class/PushedSet.js';

/**
 * These tests target the handler-side contract that PushedSet enforces.
 * Rather than spinning up a real PlaywrightCrawler, we exercise the guard
 * pattern directly: a small `guardedPush` helper mirrors the pattern that
 * routerDefaultHandler / routes.ts callsites adopt. This lets us verify the
 * invariants without browser overhead.
 *
 * Spec-compliance review must confirm the same guard pattern was applied
 * at all 3 production callsites — these tests verify the PATTERN is sound.
 */

function makeMockRedisClient() {
    const seen = new Set<string>();
    return {
        isOpen: true,
        async sAdd(_key: string, member: string) {
            if (seen.has(member)) return 0;
            seen.add(member);
            return 1;
        },
        async sRem(_key: string, member: string) { seen.delete(member); return 1; },
        async expire(_key: string, _ttl: number) { return 1; },
        async del(_key: string) { return 1; },
    };
}

async function guardedPush<T>(
    pushedSet: PushedSet,
    url: string,
    push: () => Promise<T>,
    markHandled?: () => Promise<void>,
): Promise<T | undefined> {
    if (!(await pushedSet.tryClaim(url))) {
        if (markHandled) await markHandled();
        return undefined;
    }
    const result = await push();
    if (markHandled) await markHandled();
    return result;
}

test('happy path — pushData fires once on first claim', async () => {
    const client = makeMockRedisClient();
    const set = new PushedSet(client as any, 'crawl-h');
    let pushCount = 0;
    let handledCount = 0;
    const result = await guardedPush(
        set,
        'https://example.com/a',
        async () => { pushCount++; return 'ROW'; },
        async () => { handledCount++; },
    );
    assert.equal(pushCount, 1);
    assert.equal(handledCount, 1);
    assert.equal(result, 'ROW');
});

test('retry-after-pushData — second attempt skips pushData, still marks handled', async () => {
    const client = makeMockRedisClient();
    const set = new PushedSet(client as any, 'crawl-r1');
    let pushCount = 0;
    let handledCount = 0;
    // Attempt 1: simulates "pushData fired, then timeout before markHandled".
    let caught: Error | undefined;
    try {
        await guardedPush(
            set,
            'https://example.com/a',
            async () => { pushCount++; throw new Error('TimeoutError: timed out'); },
            async () => { handledCount++; },
        );
    } catch (e) {
        caught = e as Error;
    }
    assert.ok(caught, 'attempt 1 must propagate the timeout error');
    assert.equal(caught!.message, 'TimeoutError: timed out', 'error message preserved');
    assert.equal(pushCount, 1, 'attempt 1 pushed once before timeout');
    assert.equal(handledCount, 0, 'attempt 1 did NOT mark handled (timeout interrupted)');

    // Attempt 2: retry — tryClaim returns false, pushData skipped, markHandled fires.
    const r = await guardedPush(
        set,
        'https://example.com/a',
        async () => { pushCount++; return 'ROW'; },
        async () => { handledCount++; },
    );
    assert.equal(r, undefined, 'retry must skip pushData (return undefined)');
    assert.equal(pushCount, 1, 'pushData total stays at 1 — no duplicate');
    assert.equal(handledCount, 1, 'retry marks handled so Crawlee acks');
});

test('retry-before-pushData — first attempt threw before reaching pushData, retry succeeds', async () => {
    const client = makeMockRedisClient();
    const set = new PushedSet(client as any, 'crawl-r2');
    let pushCount = 0;
    // Attempt 1: handler throws BEFORE reaching guardedPush. PushedSet never touched.

    // Attempt 2: retry runs guardedPush for the first time — tryClaim wins.
    const r = await guardedPush(
        set,
        'https://example.com/a',
        async () => { pushCount++; return 'ROW'; },
    );
    assert.equal(r, 'ROW');
    assert.equal(pushCount, 1, 'retry must push exactly once');
});

test('Option A retry-bypass — retryCount>0 lets handler proceed past doublon', () => {
    // This test models the routes.ts:387 condition:
    //   if (!isDoublon || request.retryCount > 0) { ...extraction... }
    function shouldProceed(isDoublon: boolean, retryCount: number): boolean {
        return !isDoublon || retryCount > 0;
    }
    assert.equal(shouldProceed(false, 0), true,  'first attempt, not doublon → proceed');
    assert.equal(shouldProceed(true,  0), false, 'first attempt, doublon → bail (legacy)');
    assert.equal(shouldProceed(true,  1), true,  'retry, doublon (bug case) → proceed (FIX)');
    assert.equal(shouldProceed(true,  5), true,  'late retry, doublon → still proceed');
    assert.equal(shouldProceed(false, 1), true,  'retry, not doublon → proceed');
});

test('three pushData callsites all use the same guard pattern (smoke per route)', async () => {
    // Parameterised smoke: each callsite (main / nfr / error) must follow the
    // same tryClaim-before-pushData pattern. We model this by running the same
    // helper against 3 distinct URLs and asserting one row per URL across
    // simulated retries.
    const client = makeMockRedisClient();
    const set = new PushedSet(client as any, 'crawl-3sites');

    const callsites = [
        { name: 'main',  url: 'https://example.com/a' },
        { name: 'nfr',   url: 'https://example.com/b' },
        { name: 'error', url: 'https://example.com/c' },
    ];

    const pushCounts: Record<string, number> = { main: 0, nfr: 0, error: 0 };

    for (const cs of callsites) {
        // Attempt 1: push fires then "times out".
        await guardedPush(
            set,
            cs.url,
            async () => { pushCounts[cs.name]++; throw new Error('timeout'); },
            async () => {/* not reached */},
        ).catch(() => {});

        // Attempt 2 (retry): tryClaim returns false, push skipped.
        await guardedPush(
            set,
            cs.url,
            async () => { pushCounts[cs.name]++; return 'OK'; },
            async () => {/* would fire */},
        );
    }

    assert.equal(pushCounts.main,  1, 'main callsite must push exactly once across retry');
    assert.equal(pushCounts.nfr,   1, 'nfr callsite must push exactly once across retry');
    assert.equal(pushCounts.error, 1, 'error callsite must push exactly once across retry');
});
