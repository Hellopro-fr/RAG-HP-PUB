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
    const calls: Array<[string, unknown]> = [];
    return {
        async writeLine(filename: string, data: unknown) { calls.push([filename, data]); },
        _calls: calls,
    };
}

test('checkUrl second call for same URL skips all writeJsonl invocations', async () => {
    const redis = makeMockRedisClient();
    const pushedSet = new PushedSet(redis as any, 'crawl-update');
    const consolidator = makeMockConsolidator();
    const stats = makeMockStatsManager();
    const writer = makeMockJsonlWriter();

    const checker = new UpdateChecker(
        consolidator as any,
        stats as any,
        writer as any,
        pushedSet,
    );

    // First call: not-from-dataset, success 200, French → triggers new_url emit.
    const url = 'https://example.com/page-a';
    const r1 = await checker.checkUrl(url, url, 'discovered', 200, true);
    assert.equal(r1.action, 'new_url', 'first call must emit new_url action');
    assert.equal(writer._calls.length, 1, 'first call writes exactly one JSONL line');
    assert.equal(writer._calls[0][0], UpdateChecker.NEW_URLS_FILE);

    // Second call for SAME url: PushedSet returns false → ignored, no writeJsonl.
    const r2 = await checker.checkUrl(url, url, 'discovered', 200, true);
    assert.equal(r2.action, 'ignored', 'second call must be ignored');
    assert.equal(r2.reason, 'already_pushed', 'reason must indicate the PushedSet guard fired');
    assert.equal(writer._calls.length, 1, 'second call must NOT write any new JSONL line');
    assert.equal(stats._calls.length, 1, 'second call must NOT increment any stats counter (catches future refactor moving guard below increment)');
});
