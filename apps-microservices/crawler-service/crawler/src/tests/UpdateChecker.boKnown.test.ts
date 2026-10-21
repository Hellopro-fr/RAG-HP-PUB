// A312 T04 — verdicts `bo_known` de UpdateChecker (spec §3.5, tableau des verdicts).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
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

function makeMockConsolidator(inDataset: boolean) {
    const calls: string[] = [];
    return {
        async isInDataset(url: string) { calls.push(url); return inDataset; },
        async cleanup() {},
        _calls: calls,
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

function makeChecker(inDataset = false) {
    const pushedSet = new PushedSet(makeMockRedisClient() as any, 'crawl-update');
    const stats = makeMockStatsManager();
    const writer = makeMockJsonlWriter();
    const consolidator = makeMockConsolidator(inDataset);
    const checker = new UpdateChecker(consolidator as any, stats as any, writer as any, pushedSet);
    return { checker, stats, writer, consolidator };
}

const OK = 'https://www.e.fr/produits/cuve-a.html';
const OLD = 'https://www.e.fr/ancien';
const NEW = 'https://www.e.fr/nouveau';
const RAW = 'https://www.e.fr/Produit/Cuve%20A/?ref=B%C3%A9&x=1#ancre';
const D2_COUNTERS = ['errors', 'processed', 'errors_unprocessed', 'not_eligible', 'redirects', 'new_urls', 'accounted'];

test('§3.5 ligne 404/410 : deleted http_error_<code>, bo_known_deleted', async () => {
    for (const code of [404, 410]) {
        const { checker, stats, writer } = makeChecker();
        const r = await checker.checkUrl(OK, OK, 'bo_known', code, false);
        assert.equal(r.action, 'deleted', `code ${code}`);
        assert.equal(r.reason, `http_error_${code}`);
        assert.deepEqual(stats._calls, ['bo_known_deleted']);
        assert.equal(writer._calls.length, 1);
        assert.equal(writer._calls[0][0], UpdateChecker.DELETED_FILE);
    }
});

test('§3.5 ligne 200 non éligible : deleted not_eligible, bo_known_deleted', async () => {
    const { checker, stats, writer } = makeChecker();
    const r = await checker.checkUrl(OK, OK, 'bo_known', 200, false);
    assert.equal(r.action, 'deleted');
    assert.equal(r.reason, 'not_eligible');
    assert.deepEqual(stats._calls, ['bo_known_deleted']);
    assert.equal(writer._calls.length, 1);
    assert.equal(writer._calls[0][0], UpdateChecker.DELETED_FILE);
});

test('§3.5 ligne redirection avec destination : redirected, bo_known_redirected', async () => {
    for (const status of [301, 200]) {
        const { checker, stats, writer } = makeChecker();
        const r = await checker.checkUrl(OLD, NEW, 'bo_known', status, true);
        assert.equal(r.action, 'redirected', `status ${status}`);
        assert.equal(r.destination, NEW);
        assert.equal(r.url, OLD);
        assert.deepEqual(stats._calls, ['bo_known_redirected']);
        assert.equal(writer._calls.length, 1);
        assert.equal(writer._calls[0][0], UpdateChecker.REDIRECTED_FILE);
        assert.equal(writer._calls[0][1].destination, NEW);
    }
});

test('§3.5 ligne 200 éligible : aucun événement, bo_known_alive', async () => {
    const { checker, stats, writer } = makeChecker();
    const r = await checker.checkUrl(OK, OK, 'bo_known', 200, true);
    assert.equal(r.action, 'confirmed');
    assert.deepEqual(stats._calls, ['bo_known_alive']);
    assert.deepEqual(writer._calls, [], 'ni deleted, ni redirected, ni new_urls, aucune écriture');
});

test('§3.5 ligne 403/429/5xx/0 : aucun événement, bo_known_errors', async () => {
    for (const status of [403, 429, 500, 502, 503, 0]) {
        const { checker, stats, writer } = makeChecker();
        const r = await checker.checkUrl(OK, OK, 'bo_known', status, false);
        assert.equal(r.action, 'ignored', `status ${status}`);
        assert.equal(r.reason, `unverified_http_error_${status}`);
        assert.deepEqual(stats._calls, ['bo_known_errors']);
        assert.deepEqual(writer._calls, []);
    }
});

test('§3.5 le test de redirection est celui de isRedirect : un / final seul n\'est pas une redirection', async () => {
    const { checker, stats, writer } = makeChecker();
    const r = await checker.checkUrl('https://www.e.fr/a', 'https://www.e.fr/a/', 'bo_known', 200, true);
    assert.equal(r.action, 'confirmed');
    assert.deepEqual(stats._calls, ['bo_known_alive']);
    assert.deepEqual(writer._calls, []);
});

test('§3.5 url brute à l\'octet dans le résultat et dans la ligne écrite (deleted et redirected)', async () => {
    const del = makeChecker();
    const rd = await del.checker.checkUrl(RAW, RAW, 'bo_known', 404, false);
    assert.equal(rd.action, 'deleted');
    assert.equal(rd.url, RAW);
    assert.equal(del.writer._calls[0][1].url, RAW);

    const red = makeChecker();
    const rr = await red.checker.checkUrl(RAW, NEW, 'bo_known', 200, true);
    assert.equal(rr.action, 'redirected');
    assert.equal(rr.url, RAW);
    assert.equal(red.writer._calls[0][1].url, RAW);
});

test('§3.5 origin et source bo_known dans la ligne JSONL écrite', async () => {
    const del = makeChecker();
    const rd = await del.checker.checkUrl(OK, OK, 'bo_known', 410, false);
    assert.equal(rd.action, 'deleted');
    assert.equal(del.writer._calls[0][1].origin, 'bo_known');
    assert.equal(del.writer._calls[0][1].source, 'bo_known');
    assert.ok(JSON.stringify(del.writer._calls[0][1]).includes('"origin":"bo_known"'));

    const red = makeChecker();
    const rr = await red.checker.checkUrl(OLD, NEW, 'bo_known', 200, true);
    assert.equal(rr.action, 'redirected');
    assert.equal(red.writer._calls[0][1].origin, 'bo_known');
    assert.equal(red.writer._calls[0][1].source, 'bo_known');
});

test('§3.5 une ligne native garde ses clés : aucune clé origin', async () => {
    const { checker, writer } = makeChecker(true);
    const r = await checker.checkUrl(OK, OK, 'dataset', 404, false);
    assert.equal(r.action, 'deleted');
    const keys = Object.keys(JSON.parse(JSON.stringify(writer._calls[0][1])));
    assert.deepEqual(keys, ['url', 'source', 'action', 'reason', 'timestamp']);
});

test('§3.5 aucun compteur de D2 : chaque scénario n\'écrit que son compteur bo_known_*', async () => {
    const scenarios: Array<[string, string, number, boolean, string]> = [
        [OK, OK, 404, false, 'bo_known_deleted'],
        [OK, OK, 200, false, 'bo_known_deleted'],
        [OLD, NEW, 200, true, 'bo_known_redirected'],
        [OK, OK, 200, true, 'bo_known_alive'],
        [OK, OK, 503, false, 'bo_known_errors'],
    ];
    for (const [url, loaded, status, french, expected] of scenarios) {
        const { checker, stats } = makeChecker();
        await checker.checkUrl(url, loaded, 'bo_known', status, french);
        assert.deepEqual(stats._calls, [expected], `${status} ${url}`);
        for (const name of D2_COUNTERS) {
            assert.ok(!stats._calls.includes(name), `${name} ne doit pas être incrémenté`);
        }
    }
});

test('§3.5 le consolidateur n\'est jamais interrogé pour une source bo_known', async () => {
    const gone = makeChecker(true);
    const r1 = await gone.checker.checkUrl(OK, OK, 'bo_known', 404, false);
    assert.equal(r1.action, 'deleted');
    assert.deepEqual(gone.stats._calls, ['bo_known_deleted'], 'même si le consolidateur dirait « exact »');
    assert.deepEqual(gone.consolidator._calls, []);

    const moved = makeChecker(true);
    const r2 = await moved.checker.checkUrl(OLD, NEW, 'bo_known', 200, true);
    assert.equal(r2.action, 'redirected', 'destination « dans le dataset » comprise');
    assert.deepEqual(moved.consolidator._calls, []);
});

test('§3.5 la garde PushedSet précède la branche bo_known', async () => {
    const { checker, stats, writer } = makeChecker();
    const first = await checker.checkUrl(OK, OK, 'bo_known', 404, false);
    assert.equal(first.action, 'deleted');
    const second = await checker.checkUrl(OK, OK, 'bo_known', 404, false);
    assert.equal(second.action, 'ignored');
    assert.equal(second.reason, 'already_pushed');
    assert.deepEqual(stats._calls, ['bo_known_deleted']);
    assert.equal(writer._calls.length, 1);
});

test('§3.5 source : checkBoKnown n\'incrémente que bo_known_*, et la branche suit la garde PushedSet', () => {
    const text = fs.readFileSync(path.join(import.meta.dirname, '..', 'class', 'UpdateChecker.ts'), 'utf-8');
    const start = text.indexOf('private async checkBoKnown(');
    const end = text.indexOf('    async checkUrl(');
    assert.ok(start !== -1 && end > start, 'checkBoKnown doit exister, avant checkUrl');

    const written = text.slice(start, end).match(/increment\("[a-z_]+"\)/g) ?? [];
    assert.equal(written.length, 5, 'cinq incréments : deleted x2, redirected, alive, errors');
    assert.ok(written.every((w) => w.startsWith('increment("bo_known_')), `compteurs hors bo_known_ : ${written.join(' ')}`);

    const claim = text.indexOf('this.pushedSet.tryClaim(');
    const branch = text.search(/if \(source === BO_KNOWN_SOURCE\) \{\s*return await this\.checkBoKnown\(/);
    const native = text.indexOf("const match = source === 'dataset'");
    assert.ok(claim !== -1 && branch !== -1 && native !== -1, 'les trois repères doivent exister');
    assert.ok(claim < branch && branch < native, 'ordre attendu : garde PushedSet, branche bo_known, voie native');
});
