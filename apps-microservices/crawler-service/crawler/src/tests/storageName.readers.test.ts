import { test, after } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { context } from '../context.js';

/**
 * A614 — the readers must use the names the writers use.
 *
 * The request queue and the dataset are written under the dotted domain (`RequestQueue.open(domain)`,
 * `Dataset.open(domain)`). `crawleeStorageName` (dots replaced by hyphens) only names the `error-` and
 * `pdf-` datasets (A576). Before A614, the queue rewrite after a skipDiez / Tier-2 '?' decision and the
 * restart rehydration read `crawleeStorageName`, found no folder and returned nothing, silently.
 *
 * Data is fabricated in a temporary storage dir: no server, no Redis, no network. `getAllRequestQueues`
 * and `rehydrateDedupFromDataset` read `storage/...` from the current directory, so the test chdirs into
 * the temporary dir and points CRAWLEE_STORAGE_DIR at its `storage/` subfolder.
 *
 * Cases 1-2 also run on the build (`npx tsc`, then `node --test dist/tests/storageName.readers.test.js`):
 * production runs `node dist/main.js`, and the rewrite loads functions.js through createRequire
 * (review A614, condition 1). A "Queue rewrite skipped" warning, or a queued URL still served with its
 * '#' or parameter, fails the test in both modes.
 *
 * ⚠ Case 3 pins main.ts on purpose (choice 2a, A576 pattern): main.ts is not importable (it runs at
 * load), so the test reads its text and requires every `rehydrateDedupFromDataset(...)` call to pass
 * `domain`, then replays that call on the temporary storage. On the build only main.js sits next to
 * the test: case 3 is skipped there.
 */

const TMP = fs.mkdtempSync(path.join(os.tmpdir(), 'a614-'));
const previousCwd = process.cwd();
const previousStorageDir = process.env.CRAWLEE_STORAGE_DIR;
const previousPerClass = process.env.DIEZ_PERCLASS_ENABLED;
process.env.CRAWLEE_STORAGE_DIR = path.join(TMP, 'storage');
delete process.env.DIEZ_PERCLASS_ENABLED; // legacy blind '#' strip, the processUrl path skipDiez takes by default
process.chdir(TMP);
after(() => {
    process.chdir(previousCwd);
    if (previousStorageDir === undefined) delete process.env.CRAWLEE_STORAGE_DIR;
    else process.env.CRAWLEE_STORAGE_DIR = previousStorageDir;
    if (previousPerClass !== undefined) process.env.DIEZ_PERCLASS_ENABLED = previousPerClass;
    try { fs.rmSync(TMP, { recursive: true, force: true }); } catch { /* best-effort (Windows file locks) */ }
});

// Imported once CRAWLEE_STORAGE_DIR points at TMP, so every storage opened below lives there.
// functions.js is loaded before the decisions run, as in production (main.js imports it at startup).
const { RequestQueue, Dataset } = await import('crawlee');
const { rehydrateDedupFromDataset } = await import('../functions.js');
const { commitSkipDiez } = await import('../diezDecision.js');
const { commitToRemoveParam } = await import('../questionMarkTier2.js');

const MAIN_TS = path.join(import.meta.dirname, '..', 'main.ts');

// Full-line `//` comments blanked: a commented-out call can neither satisfy nor break case 3.
const blankLineComments = (s: string) => s.replace(/^[ \t]*\/\/.*$/gm, (m) => ' '.repeat(m.length));

/** Crawlee persists queue/dataset entries asynchronously: wait until `count` entry files are on disk. */
const waitForJsonFiles = async (dir: string, count: number): Promise<string[]> => {
    const deadline = Date.now() + 10_000;
    for (;;) {
        const files = fs.existsSync(dir)
            ? fs.readdirSync(dir).filter((f) => f.endsWith('.json') && !f.startsWith('__'))
            : [];
        if (files.length >= count) return files.map((f) => path.join(dir, f));
        if (Date.now() > deadline) assert.fail(`expected ${count} entry file(s) in ${dir}, found ${files.length}`);
        await new Promise((r) => setTimeout(r, 50));
    }
};

const queuedUrlsOnDisk = (files: string[]) =>
    files.map((f) => JSON.parse(fs.readFileSync(f, 'utf-8')) as { url: string; json: string })
        .map((e) => ({ url: e.url, inner: (JSON.parse(e.json) as { url: string }).url }))
        .sort((a, b) => a.url.localeCompare(b.url));

const drain = async (queue: Awaited<ReturnType<typeof RequestQueue.open>>): Promise<string[]> => {
    const served: string[] = [];
    for (let r = await queue.fetchNextRequest(); r; r = await queue.fetchNextRequest()) {
        served.push(r.url);
        await queue.markRequestHandled(r);
    }
    return served.sort();
};

test("case 1: skipDiez rewrites the dotted-domain queue and logs '[diez] Rewrote'", async (t) => {
    const domain = 'diez.a614.example';
    const storageName = domain.replace(/\./g, '-'); // as main.ts sets crawleeStorageName
    const saved = {
        domain: context.config.domain,
        storageName: context.config.crawleeStorageName,
        skipDiez: context.config.skipDiez,
        skipQuestionMark: context.config.skipQuestionMark,
        toKeep: context.config.toKeep,
        toRemove: context.config.toRemove,
        committed: context.diezDecisionCommitted,
    };
    Object.assign(context.config, { domain, crawleeStorageName: storageName, skipDiez: false, skipQuestionMark: false, toKeep: [], toRemove: [] });
    context.diezDecisionCommitted = false;
    t.after(() => {
        Object.assign(context.config, {
            domain: saved.domain, crawleeStorageName: saved.storageName, skipDiez: saved.skipDiez,
            skipQuestionMark: saved.skipQuestionMark, toKeep: saved.toKeep, toRemove: saved.toRemove,
        });
        context.diezDecisionCommitted = saved.committed;
    });

    // Queue under the dotted domain, as main.ts opens it.
    const queue = await RequestQueue.open(domain);
    await queue.addRequests([`https://${domain}/p#a`, `https://${domain}/q#b`].map((url) => ({ url })));
    const queueDir = path.join('storage', 'request_queues', domain);
    const files = await waitForJsonFiles(queueDir, 2);
    const allJson = fs.readdirSync(queueDir).filter((f) => f.endsWith('.json')).length; // what getAllRequestQueues lists

    const log = t.mock.method(console, 'log', () => {});
    const warn = t.mock.method(console, 'warn', () => {});
    commitSkipDiez(TMP);
    const lines = log.mock.calls.map((c) => c.arguments.join(' '));
    const warnings = warn.mock.calls.map((c) => c.arguments.join(' '));
    log.mock.restore();
    warn.mock.restore();

    assert.ok(
        !warnings.some((w) => w.includes('Queue rewrite skipped')),
        `the rewrite must load functions.js and run; warnings: ${JSON.stringify(warnings)}`,
    );
    assert.ok(
        lines.some((l) => l.startsWith(`[diez] Rewrote ${allJson} queued request file(s) to strip '#'`)),
        `expected "[diez] Rewrote ${allJson} queued request file(s) to strip '#'"; logs: ${JSON.stringify(lines)}`,
    );
    assert.deepEqual(queuedUrlsOnDisk(files), [
        { url: `https://${domain}/p`, inner: `https://${domain}/p` },
        { url: `https://${domain}/q`, inner: `https://${domain}/q` },
    ], 'the queued request files under the dotted domain must lose their #');
    assert.equal(fs.existsSync(path.join('storage', 'request_queues', storageName)), false, 'no hyphenated queue folder');

    // What Crawlee serves next from the open queue (the cached-head limit, qmConsumptionSkip.ts).
    assert.deepEqual(await drain(queue), [`https://${domain}/p`, `https://${domain}/q`], 'Crawlee must serve the rewritten URLs');
});

test("case 2: a Tier-2 '?' decision rewrites the dotted-domain queue", async (t) => {
    const domain = 'qm.a614.example';
    const storageName = domain.replace(/\./g, '-');
    const saved = {
        domain: context.config.domain,
        storageName: context.config.crawleeStorageName,
        skipDiez: context.config.skipDiez,
        skipQuestionMark: context.config.skipQuestionMark,
        toKeep: context.config.toKeep,
        toRemove: context.config.toRemove,
        qmTier2: context.qmTier2,
    };
    Object.assign(context.config, { domain, crawleeStorageName: storageName, skipDiez: false, skipQuestionMark: false, toKeep: [], toRemove: [] });
    context.qmTier2 = { active: true, contentByUrl: new Map(), groups: new Map(), tally: new Map(), decided: new Set(), addedToRemove: [], contentShaping: [], defaulted: false };
    t.after(() => {
        Object.assign(context.config, {
            domain: saved.domain, crawleeStorageName: saved.storageName, skipDiez: saved.skipDiez,
            skipQuestionMark: saved.skipQuestionMark, toKeep: saved.toKeep, toRemove: saved.toRemove,
        });
        context.qmTier2 = saved.qmTier2;
    });

    const queue = await RequestQueue.open(domain);
    await queue.addRequests([{ url: `https://${domain}/r?utm=1&id=7` }]);
    const queueDir = path.join('storage', 'request_queues', domain);
    const files = await waitForJsonFiles(queueDir, 1);

    const log = t.mock.method(console, 'log', () => {});
    const warn = t.mock.method(console, 'warn', () => {});
    commitToRemoveParam('utm', TMP);
    const warnings = warn.mock.calls.map((c) => c.arguments.join(' '));
    log.mock.restore();
    warn.mock.restore();

    assert.ok(
        !warnings.some((w) => w.includes('Queue rewrite skipped')),
        `the rewrite must load functions.js and run; warnings: ${JSON.stringify(warnings)}`,
    );
    assert.deepEqual(queuedUrlsOnDisk(files), [{ url: `https://${domain}/r?id=7`, inner: `https://${domain}/r?id=7` }],
        'the queued request file under the dotted domain must lose utm');
    assert.equal(fs.existsSync(path.join('storage', 'request_queues', storageName)), false, 'no hyphenated queue folder');
    assert.deepEqual(await drain(queue), [`https://${domain}/r?id=7`], 'Crawlee must serve the rewritten URL');
});

test(
    'case 3: restart re-reads the dotted-domain dataset (main.ts passes domain)',
    { skip: fs.existsSync(MAIN_TS) ? false : 'main.ts absent next to the test (build): case 3 runs under tsx only' },
    async (t) => {
        const main = blankLineComments(fs.readFileSync(MAIN_TS, 'utf-8'));
        const args = [...main.matchAll(/\brehydrateDedupFromDataset\(([^)]*)\)/g)].map((m) => m[1].trim());
        assert.deepEqual(args, ['domain', 'domain', 'domain'],
            `main.ts must call rehydrateDedupFromDataset(domain) at its 3 restart reads (hot counters, cold dedup, seenBases); found ${JSON.stringify(args)}`);

        // Replay the call as main.ts makes it (`domain`), on a dataset written the way pages are written.
        const domain = 'restart.a614.example';
        const dataset = await Dataset.open(domain);
        await dataset.pushData([{ url: `https://${domain}/a?x=1#y` }, { url: `https://${domain}/b` }]);
        await waitForJsonFiles(path.join('storage', 'datasets', domain), 2);

        const log = t.mock.method(console, 'log', () => {});
        const urls: string[] = [];
        for await (const u of rehydrateDedupFromDataset(domain)) urls.push(u);
        const lines = log.mock.calls.map((c) => c.arguments.join(' '));
        log.mock.restore();

        assert.ok(
            lines.some((l) => l.startsWith('Rehydrating Dedup from current dataset: ')
                && l.endsWith(path.join('storage', 'datasets', domain))),
            `expected "Rehydrating Dedup from current dataset: …${path.join('storage', 'datasets', domain)}"; logs: ${JSON.stringify(lines)}`,
        );
        assert.deepEqual(urls.sort(), [`https://${domain}/a?x=1#y`, `https://${domain}/b`]);
    },
);
