// Repeatable redirect signal (incident 1079-327): redirect_to_existing* branches
// must still RECORD the old→new mapping in redirected_urls.jsonl (so the BO can
// retire a leftover old fiche on ANY later MAJ), WITHOUT incrementing the
// 'redirects' stat (which feeds the circuit breaker / health report rates).
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

function makeMockConsolidator(destInDataset: boolean) {
    return {
        async isInDataset(_url: string) { return destInDataset; },
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

function makeChecker(destInDataset: boolean) {
    const pushedSet = new PushedSet(makeMockRedisClient() as any, 'crawl-update');
    const stats = makeMockStatsManager();
    const writer = makeMockJsonlWriter();
    const checker = new UpdateChecker(
        makeMockConsolidator(destInDataset) as any,
        stats as any,
        writer as any,
        pushedSet,
    );
    return { checker, stats, writer };
}

const OLD = 'https://example.com/old-cat/product-1.html';
const NEW = 'https://example.com/new-cat/product-1.html';

test('dataset redirect to existing dataset URL: recorded in jsonl, no redirects counter', async () => {
    const { checker, stats, writer } = makeChecker(true);
    const r = await checker.checkUrl(OLD, NEW, 'dataset', 200, true);
    assert.equal(r.action, 'confirmed');
    assert.equal(r.reason, 'redirect_to_existing');
    assert.equal(writer._calls.length, 1, 'mapping must be recorded');
    assert.equal(writer._calls[0][0], UpdateChecker.REDIRECTED_FILE);
    assert.equal(writer._calls[0][1].url, OLD);
    assert.equal(writer._calls[0][1].destination, NEW);
    assert.ok(!stats._calls.includes('redirects'), 'must NOT feed the circuit breaker');
});

test('non-dataset redirect to existing dataset URL: recorded in jsonl, no redirects counter', async () => {
    const { checker, stats, writer } = makeChecker(true);
    const r = await checker.checkUrl(OLD, NEW, 'request_queue', 200, true);
    assert.equal(r.action, 'ignored');
    assert.equal(r.reason, 'redirect_to_existing_dataset');
    assert.equal(writer._calls.length, 1, 'mapping must be recorded');
    assert.equal(writer._calls[0][0], UpdateChecker.REDIRECTED_FILE);
    assert.equal(writer._calls[0][1].destination, NEW);
    assert.ok(!stats._calls.includes('redirects'), 'must NOT feed the circuit breaker');
});

test('regression: dataset redirect to NEW destination still counts + records once', async () => {
    const { checker, stats, writer } = makeChecker(false);
    const r = await checker.checkUrl(OLD, NEW, 'dataset', 200, true);
    assert.equal(r.action, 'redirected');
    assert.equal(writer._calls.length, 1);
    assert.equal(writer._calls[0][0], UpdateChecker.REDIRECTED_FILE);
    assert.deepEqual(stats._calls, ['redirects', 'accounted'], 'genuinely-new redirect still feeds the counter');
});
