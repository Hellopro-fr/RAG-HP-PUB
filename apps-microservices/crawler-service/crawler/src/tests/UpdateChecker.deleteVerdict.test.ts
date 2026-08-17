// Deletion verdict gate (incident 1320-402): a dataset URL may be claimed
// 'deleted' ONLY on a server GONE verdict (404/410). Blocks and outages
// (401/403/429/5xx/status-0) still count as errors (health/circuit-breaker
// unchanged) but must NOT emit a deleted event — 63 anti-bot 403s became 59
// false fiche deletions BO-side on mtdfrance.fr.
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
    const calls: Array<[string, any]> = [];
    return {
        async writeLine(filename: string, data: any) { calls.push([filename, data]); },
        _calls: calls,
    };
}

function makeChecker() {
    const pushedSet = new PushedSet(makeMockRedisClient() as any, 'crawl-update');
    const stats = makeMockStatsManager();
    const writer = makeMockJsonlWriter();
    const checker = new UpdateChecker(
        makeMockConsolidator() as any,
        stats as any,
        writer as any,
        pushedSet,
    );
    return { checker, stats, writer };
}

const URL404 = 'https://example.com/produits/gone.html';

test('dataset 404: deleted event written, errors counted', async () => {
    const { checker, stats, writer } = makeChecker();
    const r = await checker.checkUrl(URL404, URL404, 'dataset', 404, false);
    assert.equal(r.action, 'deleted');
    assert.equal(r.reason, 'http_error_404');
    assert.equal(writer._calls.length, 1);
    assert.equal(writer._calls[0][0], UpdateChecker.DELETED_FILE);
    assert.deepEqual(stats._calls, ['errors', 'accounted']);
});

test('dataset 410: deleted event written', async () => {
    const { checker, writer } = makeChecker();
    const r = await checker.checkUrl(URL404, URL404, 'dataset', 410, false);
    assert.equal(r.action, 'deleted');
    assert.equal(writer._calls.length, 1);
});

test('dataset 403 (anti-bot block): NO deleted event, still counts as error', async () => {
    const { checker, stats, writer } = makeChecker();
    const r = await checker.checkUrl(URL404, URL404, 'dataset', 403, false);
    assert.equal(r.action, 'ignored');
    assert.equal(r.reason, 'unverified_http_error_403');
    assert.equal(writer._calls.length, 0, 'no deleted event for a block');
    assert.deepEqual(stats._calls, ['errors'], 'error still feeds health/circuit-breaker');
});

test('dataset 429/500/503/status-0: NO deleted event', async () => {
    for (const status of [429, 500, 503, 0]) {
        const { checker, writer } = makeChecker();
        const r = await checker.checkUrl(URL404, URL404, 'dataset', status, false);
        assert.equal(r.action, 'ignored', `status ${status}`);
        assert.equal(r.reason, `unverified_http_error_${status}`, `status ${status}`);
        assert.equal(writer._calls.length, 0, `status ${status}: no deleted event`);
    }
});

test('non-dataset error: unchanged (ignored, non_dataset_error, no error counter)', async () => {
    const { checker, stats, writer } = makeChecker();
    const r = await checker.checkUrl(URL404, URL404, 'discovered', 403, false);
    assert.equal(r.action, 'ignored');
    assert.equal(r.reason, 'non_dataset_error');
    assert.equal(writer._calls.length, 0);
    assert.deepEqual(stats._calls, []);
});
