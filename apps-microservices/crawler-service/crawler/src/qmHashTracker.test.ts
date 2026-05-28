/**
 * Tests for qmHashTracker.trackQmHashStatsForUrl().
 *
 * Validates that the helper mirrors the right StatsManager counter for URLs
 * containing '?' or '#', without double-counting and without crashing when
 * the StatsManager is absent.
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { trackQmHashStatsForUrl } from './qmHashTracker.js';

interface IncrementCall {
    counter: string;
    by?: number;
}

function makeMockStatsManager() {
    const calls: IncrementCall[] = [];
    return {
        async increment(counter: string, by?: number) {
            calls.push({ counter, by });
        },
        _calls: calls,
    };
}

test('trackQmHashStatsForUrl: URL without ? or # does not increment any counter', () => {
    const stats = makeMockStatsManager();
    trackQmHashStatsForUrl('https://example.com/page-without-anything', stats as any);
    assert.equal(stats._calls.length, 0, 'no increment expected for plain URL');
});

test('trackQmHashStatsForUrl: URL with ? increments filtered_qm only', () => {
    const stats = makeMockStatsManager();
    trackQmHashStatsForUrl('https://example.com/page?id=42', stats as any);
    assert.equal(stats._calls.length, 1);
    assert.equal(stats._calls[0].counter, 'filtered_qm');
});

test('trackQmHashStatsForUrl: URL with # increments filtered_hash only', () => {
    const stats = makeMockStatsManager();
    trackQmHashStatsForUrl('https://example.com/page#section-2', stats as any);
    assert.equal(stats._calls.length, 1);
    assert.equal(stats._calls[0].counter, 'filtered_hash');
});

test('trackQmHashStatsForUrl: URL with both ? and # increments both counters once each', () => {
    const stats = makeMockStatsManager();
    trackQmHashStatsForUrl('https://example.com/page?id=42#section', stats as any);
    assert.equal(stats._calls.length, 2);
    const counters = stats._calls.map(c => c.counter).sort();
    assert.deepEqual(counters, ['filtered_hash', 'filtered_qm']);
});

test('trackQmHashStatsForUrl: each call increments at most once per counter (no double-count)', () => {
    const stats = makeMockStatsManager();
    // URL avec plusieurs `?` (illégal HTTP mais bien défensif côté code)
    trackQmHashStatsForUrl('https://example.com/page?a=1?b=2', stats as any);
    const qmCalls = stats._calls.filter(c => c.counter === 'filtered_qm');
    assert.equal(qmCalls.length, 1, 'filtered_qm must be incremented exactly once per call');
});

test('trackQmHashStatsForUrl: undefined statsManager is a no-op (no crash)', () => {
    // Doit pas crasher quand statsManager est absent (cas init avant connect Redis).
    assert.doesNotThrow(() => {
        trackQmHashStatsForUrl('https://example.com/page?id=42#section', undefined);
    });
});

test('trackQmHashStatsForUrl: null statsManager is a no-op (no crash)', () => {
    // context.statsManager peut être typé `StatsManager | null` côté crawler.
    assert.doesNotThrow(() => {
        trackQmHashStatsForUrl('https://example.com/page?id=42#section', null);
    });
});

test('trackQmHashStatsForUrl: regression — pure `?` triggers filtered_qm', () => {
    const stats = makeMockStatsManager();
    trackQmHashStatsForUrl('https://example.com/?', stats as any);
    assert.equal(stats._calls.length, 1);
    assert.equal(stats._calls[0].counter, 'filtered_qm');
});

test('trackQmHashStatsForUrl: regression — pure `#` triggers filtered_hash', () => {
    const stats = makeMockStatsManager();
    trackQmHashStatsForUrl('https://example.com/page#', stats as any);
    assert.equal(stats._calls.length, 1);
    assert.equal(stats._calls[0].counter, 'filtered_hash');
});
