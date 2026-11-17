import { test, after } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { context } from '../context.js';

/**
 * A576 — restart recovery and the `dropData` launch must target the error dataset the
 * failures are actually written to.
 *
 * Both writers (failure handler in functions.ts, unresolved-challenge homepage in routes.ts)
 * write to `error-${context.config.crawleeStorageName}`: the domain with its dots replaced by
 * hyphens (main.ts, `crawleeStorageName`). The request queue, though, is opened under the
 * dotted domain. So `reclaimFailedRequest(domain)` must read the hyphenated dataset and
 * re-queue into the dotted queue (test 1), and a `dropdata` launch must empty the hyphenated
 * dataset (test 2). Both fail on de5724070, where the reader and dropData only used
 * `error-${domain}`, a name no writer has used since 2026-01-29.
 *
 * Data is fabricated in a temporary Crawlee storage dir: no server, no Redis, no network.
 *
 * ⚠ Test 2 pins main.ts on purpose (review A576, point 4). main.ts is not importable (it runs
 * at load), so the test reads its text: it takes the `dropDataset(...)` calls inside
 * `if (dropData) {`, resolves `domain` and `${context.config.crawleeStorageName}` without eval,
 * and replays them on the temporary storage. It turns red if that anchor is renamed, if the
 * hyphenated or the dotted `error-` line is removed, or if a call passes any other expression.
 * Before adapting it, check that a `dropdata` launch still empties the hyphenated dataset.
 */

const TMP = fs.mkdtempSync(path.join(os.tmpdir(), 'a576-'));
const previousStorageDir = process.env.CRAWLEE_STORAGE_DIR;
process.env.CRAWLEE_STORAGE_DIR = TMP;
after(() => {
    if (previousStorageDir === undefined) delete process.env.CRAWLEE_STORAGE_DIR;
    else process.env.CRAWLEE_STORAGE_DIR = previousStorageDir;
    fs.rmSync(TMP, { recursive: true, force: true });
});

// Imported once CRAWLEE_STORAGE_DIR points at TMP, so every storage opened below lives there.
const { Dataset, RequestQueue } = await import('crawlee');
const { reclaimFailedRequest, dropDataset } = await import('../functions.js');

// Full-line `//` comments blanked: a commented-out call can neither satisfy nor break test 2.
const blankLineComments = (s: string) => s.replace(/^[ \t]*\/\/.*$/gm, (m) => ' '.repeat(m.length));

test('reclaim reads error-<crawleeStorageName> and re-queues into the dotted-domain queue', async (t) => {
    const domain = 'reclaimtest.a576.example';
    const storageName = domain.replace(/\./g, '-'); // as main.ts sets crawleeStorageName
    const previousStorageName = context.config.crawleeStorageName;
    context.config.crawleeStorageName = storageName;
    t.after(() => {
        context.config.crawleeStorageName = previousStorageName;
    });

    // Queue under the dotted domain, as main.ts opens it. A request that exhausted its
    // retries is handled in the queue when its failure is written.
    const queue = await RequestQueue.open(domain);
    const urls = ['infra', 'permanent', 'legacy'].map((p) => `https://${domain}/${p}`);
    const { processedRequests } = await queue.addRequests(urls.map((url) => ({ url })));
    const ids = processedRequests.map((p) => p.requestId);
    for (let r = await queue.fetchNextRequest(); r; r = await queue.fetchNextRequest()) {
        await queue.markRequestHandled(r);
    }

    // Failures under the hyphenated name, as both writers name the dataset.
    const errors = await Dataset.open(`error-${storageName}`);
    await errors.pushData([
        { id: ids[0], url: urls[0], failure_class: 'infra' }, // recoverable
        { id: ids[1], url: urls[1], failure_class: 'permanent' }, // skipped
        { id: ids[2], url: urls[2] }, // legacy record, no failure_class: recoverable
    ]);

    const log = t.mock.method(console, 'log', () => {});
    await reclaimFailedRequest(domain); // as main.ts calls it
    const lines = log.mock.calls.map((c) => c.arguments.join(' '));
    log.mock.restore();

    assert.ok(
        lines.some((l) => l.startsWith(`Checking for failed requests in error-${storageName} (3 items)`)),
        `the hyphenated error dataset must be read; logs: ${JSON.stringify(lines)}`,
    );
    assert.ok(
        lines.some((l) => l.startsWith('Reclaimed 2 recoverable requests, skipped 1 permanent')),
        `expected 'Reclaimed 2 recoverable requests, skipped 1 permanent'; logs: ${JSON.stringify(lines)}`,
    );

    const [infra, permanent, legacy] = await Promise.all(ids.map((id) => queue.getRequest(id)));
    assert.ok(infra && !infra.handledAt, 'the infra failure must be pending again in the dotted queue');
    assert.ok(legacy && !legacy.handledAt, 'the legacy failure must be pending again in the dotted queue');
    assert.ok(permanent?.handledAt, 'the permanent failure must stay handled');
    assert.equal((await queue.getInfo())?.pendingRequestCount, 2);
});

test('dropData empties error-<crawleeStorageName> and keeps the dotted error- line', async () => {
    const domain = 'droptest.a576.example';
    const storageName = domain.replace(/\./g, '-');

    const main = blankLineComments(fs.readFileSync(path.join(import.meta.dirname, '..', 'main.ts'), 'utf-8'));
    const start = main.indexOf('if (dropData) {');
    assert.notEqual(start, -1, "anchor 'if (dropData) {' not found in main.ts");
    let depth = 0;
    let end = -1;
    for (let i = main.indexOf('{', start); i < main.length && end === -1; i++) {
        if (main[i] === '{') depth++;
        else if (main[i] === '}' && --depth === 0) end = i;
    }
    assert.notEqual(end, -1, 'end of the dropData block not found in main.ts');
    const block = main.slice(start, end + 1);

    // `domain`, or a template literal whose only placeholders are ${domain} and
    // ${context.config.crawleeStorageName}. Anything else fails: no eval.
    const resolve = (arg: string): string => {
        if (arg === 'domain') return domain;
        const tpl = /^`([^`]*)`$/.exec(arg);
        if (!tpl) assert.fail(`unexpected dropDataset argument in main.ts: ${arg}`);
        const name = tpl[1]
            .replaceAll('${domain}', domain)
            .replaceAll('${context.config.crawleeStorageName}', storageName);
        if (name.includes('${')) assert.fail(`unexpected expression in dropDataset argument: ${arg}`);
        return name;
    };
    const names = [...block.matchAll(/\bdropDataset\(([^)]*)\)/g)].map((m) => resolve(m[1].trim()));
    assert.ok(names.includes(`error-${domain}`), `the dotted error- line must stay; calls: ${JSON.stringify(names)}`);

    const errors = await Dataset.open(`error-${storageName}`);
    await errors.pushData([
        { id: 'stale-1', url: `https://${domain}/a`, failure_class: 'infra' },
        { id: 'stale-2', url: `https://${domain}/b`, failure_class: 'transient' },
    ]);
    assert.equal((await errors.getInfo())?.itemCount, 2);

    for (const name of names) await dropDataset(name);

    const reopened = await Dataset.open(`error-${storageName}`);
    assert.equal(
        (await reopened.getInfo())?.itemCount ?? 0,
        0,
        `error-${storageName} must be empty after the dropData calls ${JSON.stringify(names)}`,
    );
});
