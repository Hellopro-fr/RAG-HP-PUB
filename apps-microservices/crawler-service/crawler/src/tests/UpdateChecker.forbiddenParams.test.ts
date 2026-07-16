/**
 * Tests for UpdateChecker.hasForbiddenParams() purity.
 *
 * Background: the previous implementation incremented `filtered_qm` as a
 * side-effect inside `hasForbiddenParams()`. That increment is now centralised
 * in routes.ts via the qmHashTracker helper (covers every URL with '?', not
 * just URLs with forbidden params), so this side-effect was removed to avoid
 * double-counting.
 *
 * These tests pin that behaviour: `hasForbiddenParams()` returns the correct
 * boolean without touching the StatsManager.
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { UpdateChecker } from '../class/UpdateChecker.js';
import { PushedSet } from '../class/PushedSet.js';

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

function makeMockConsolidator() {
    return {
        async isInDataset(_url: string) { return false; },
        async cleanup() {},
    };
}

function makeMockStatsManager() {
    const calls: string[] = [];
    return {
        async increment(counter: string) { calls.push(counter); },
        _calls: calls,
    };
}

function makeMockJsonlWriter() {
    return {
        async writeLine(_filename: string, _data: unknown) {},
    };
}

function buildChecker() {
    const redis = makeMockRedisClient();
    const pushedSet = new PushedSet(redis as any, 'crawl-forbidden-params-test');
    const consolidator = makeMockConsolidator();
    const stats = makeMockStatsManager();
    const writer = makeMockJsonlWriter();

    const checker = new UpdateChecker(
        consolidator as any,
        stats as any,
        writer as any,
        pushedSet,
    );

    return { checker, stats };
}

test('hasForbiddenParams: returns true for URL with `sort` param', () => {
    const { checker, stats } = buildChecker();
    const result = (checker as any).hasForbiddenParams('https://example.com/list?sort=price_asc');
    assert.equal(result, true, 'sort is a FORBIDDEN_PARAM, should match');
    assert.equal(stats._calls.length, 0, 'hasForbiddenParams must NOT touch the StatsManager');
});

test('hasForbiddenParams: returns true for URL with `limit` param', () => {
    const { checker, stats } = buildChecker();
    const result = (checker as any).hasForbiddenParams('https://example.com/products?limit=24');
    assert.equal(result, true, 'limit is a FORBIDDEN_PARAM, should match');
    assert.equal(stats._calls.length, 0, 'no stats increment expected');
});

test('hasForbiddenParams: returns true for URL with `offset` param', () => {
    const { checker, stats } = buildChecker();
    const result = (checker as any).hasForbiddenParams('https://example.com/results?offset=20');
    assert.equal(result, true, 'offset is a FORBIDDEN_PARAM, should match');
    assert.equal(stats._calls.length, 0, 'no stats increment expected');
});

test('hasForbiddenParams: returns false for URL with only safe params', () => {
    const { checker, stats } = buildChecker();
    const result = (checker as any).hasForbiddenParams('https://example.com/product?id=42&lang=fr');
    assert.equal(result, false, 'id and lang are not in FORBIDDEN_PARAMS');
    assert.equal(stats._calls.length, 0, 'no stats increment expected');
});

test('hasForbiddenParams: returns false for URL without query string', () => {
    const { checker, stats } = buildChecker();
    const result = (checker as any).hasForbiddenParams('https://example.com/about');
    assert.equal(result, false);
    assert.equal(stats._calls.length, 0);
});

test('hasForbiddenParams: returns false for malformed URL (catch path)', () => {
    const { checker, stats } = buildChecker();
    const result = (checker as any).hasForbiddenParams('::: not a url :::');
    assert.equal(result, false, 'malformed URL must return false, not throw');
    assert.equal(stats._calls.length, 0);
});

test('hasForbiddenParams: regression — never calls filtered_qm increment in any case', () => {
    const { checker, stats } = buildChecker();
    // Mix de cas (forbidden, safe, malformé) en un seul scénario.
    (checker as any).hasForbiddenParams('https://example.com/?sort=desc');
    (checker as any).hasForbiddenParams('https://example.com/?id=1');
    (checker as any).hasForbiddenParams('https://example.com/');
    (checker as any).hasForbiddenParams('not a url');
    // Pin : aucun appel à increment depuis hasForbiddenParams.
    assert.equal(
        stats._calls.length,
        0,
        'hasForbiddenParams must remain pure — increments belong in routes.ts via qmHashTracker',
    );
});
