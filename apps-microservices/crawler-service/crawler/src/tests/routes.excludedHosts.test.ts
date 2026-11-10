// A545 — câblage des hôtes exclus dans routes.ts et main.ts. Assertions sur le texte source :
// routes.ts (handler Crawlee) et main.ts (point d'entrée) ne sont pas exécutables par le runner —
// même méthode que routes.boKnownStop.test.ts et statNameParity.test.ts.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

const read = (f: string) => fs.readFileSync(path.join(import.meta.dirname, '..', f), 'utf-8');
// Commentaires pleine ligne blanchis à longueur égale : un commentaire qui cite un littéral ne
// peut ni satisfaire ni casser une assertion.
const blank = (t: string) => t.replace(/^[ \t]*\/\/.*$/gm, (m) => ' '.repeat(m.length));
const rawRoutes = read('routes.ts');
const routes = blank(rawRoutes);
const rawMain = read('main.ts');
const main = blank(rawMain);

function count(text: string, needle: string): number {
    return text.split(needle).length - 1;
}

function only(needle: string, text: string): number {
    assert.equal(count(text, needle), 1, `"${needle}" must appear exactly once`);
    return text.indexOf(needle);
}

// Branche (b) : du test d'exclusion jusqu'à la garde hors domaine qui la suit.
function branchB(): string {
    const start = only('if (isExcludedHost(hostname, context.config.excludeHosts)) {', routes);
    const end = only('if (!isInternal) {', routes);
    assert.ok(start < end, 'branch (b) must come before `if (!isInternal) {`');
    return routes.slice(start, end);
}

test('(a) mise en file : excluded-host après external-domain, avant Queue-purge #1', () => {
    const external = only("logBlocked('external-domain', request.url);", routes);
    const excluded = only("logBlocked('excluded-host', request.url);", routes);
    const purge1 = only('// Queue-purge #1', rawRoutes);
    assert.ok(external < excluded, "excluded-host must follow the 'external-domain' check");
    assert.ok(excluded < purge1, 'excluded-host must sit before `// Queue-purge #1`');
    const guard = routes.lastIndexOf('if (isExcludedHost(reqHost, context.config.excludeHosts)) {', excluded);
    assert.ok(guard > external, 'the enqueue guard must test the host of the discovered URL (reqHost)');
});

test('(b) handler : entre `const isInternal` et `if (!isInternal) {`, qui reste unique', () => {
    const isInternal = only('const isInternal = ', routes);
    const offDomain = only('if (!isInternal) {', routes);
    const b = only('if (isExcludedHost(hostname, context.config.excludeHosts)) {', routes);
    assert.ok(isInternal < b && b < offDomain, 'branch (b) must sit between `const isInternal` and `if (!isInternal) {`');
    // hostname = hôte de request.loadedUrl (après redirection), pas de request.url.
    const loaded = only('let url = request.loadedUrl;', routes);
    const urlObj = only('const urlObj = new URL(url);', routes);
    const hostname = only('const hostname = urlObj.hostname;', routes);
    assert.ok(loaded < urlObj && urlObj < hostname && hostname < b,
        'branch (b) must test the host of request.loadedUrl');
});

test('(b) : ni external_redirects, ni disjoncteur, ni fatalExitCode, ni stopCrawler, ni processed', () => {
    const slice = branchB();
    for (const banned of [
        'external_redirects',
        'shouldTripExternalRedirectBreaker',
        'domainChanged',
        'fatalExitCode',
        'stopCrawler',
        'processed',
        'updateChecker.checkUrl',
        'pushData',
    ]) {
        assert.ok(!slice.includes(banned), `branch (b) must not contain "${banned}"`);
    }
    assert.ok(!/if \(source === BO_KNOWN_SOURCE\) \{\s*return;\s*\}/.test(slice),
        'branch (b) must not use the bo_known early-return form pinned by routes.boKnownStop.test.ts');
    assert.match(slice, /return;\s*\}\s*$/, 'branch (b) must end with its return;');
});

test('(b) : requête connue du BO ⇒ recordBoKnownUnjudged() seul ; native ⇒ excluded_host', () => {
    const slice = branchB();
    const boKnown = slice.indexOf('if (request.userData.source === BO_KNOWN_SOURCE) {');
    const unjudged = slice.indexOf('await context.updateChecker.recordBoKnownUnjudged();');
    const elseNative = slice.indexOf('} else {', boKnown);
    const increment = slice.indexOf('increment("excluded_host")');
    assert.ok(boKnown !== -1 && unjudged > boKnown && unjudged < elseNative,
        'recordBoKnownUnjudged() must be called under source === BO_KNOWN_SOURCE');
    assert.ok(increment > elseNative, 'excluded_host must be counted only for a native request');
    const homepage = slice.indexOf("context.crawlErrorMessage = \"La page d'accueil est sur un hôte exclu\"");
    assert.ok(homepage > elseNative, 'the excluded-homepage message must be native-only');
    assert.ok(!slice.includes("L'URL après la page d'accueil change de domaine"),
        'the excluded-homepage message must differ from the domain-change message');
});

test('parité des noms : routes.ts incrémente ce que main.ts lit et envoie au BO', () => {
    assert.equal(count(routes, 'increment("excluded_host")'), 1);
    assert.equal(count(routes, 'increment("excluded_host_link", excludedHostLinks)'), 1);
    assert.equal(count(main, 'readStat("excluded_host")'), 1);
    assert.equal(count(main, 'readStat("excluded_host_link")'), 1);
    assert.match(main,
        /^\s*\.\.\.\(context\.config\.excludeHosts\.length > 0 \? \{ excluded_host, excluded_host_link \} : \{\}\),\s*$/m,
        'both counters must reach the BO report, and only for a job with an exclusion list');
});

test('excluded_host_link : compté au vidage dédoublonné des URL bloquées', () => {
    const flush = only('await context.dedupManager.filterNewBlockedBatch(allUrls);', routes);
    const tally = only("if (item.reason === 'excluded-host') excludedHostLinks++;", routes);
    const inc = only('increment("excluded_host_link", excludedHostLinks)', routes);
    assert.ok(flush < tally && tally < inc, 'distinct new URLs are tallied after the Redis dedup, then counted once');
    assert.ok(routes.lastIndexOf('loggedLocal.add(item.url);', tally) > flush,
        'the tally must sit in the dedup branch (one URL counts once)');
});

test('main.ts : argument lu comme tokeep/toremove et posé dans context.config', () => {
    assert.equal(count(main, "parseExcludedHosts(getArg('excludehosts', 'npm_config_excludehosts'))"), 1);
    assert.match(main, /^\s*excludeHosts: excludeHosts,\s*$/m);
});

test('interdits du brief : contrôles includes, same-domain et ligne isMicroMode intacts', () => {
    assert.ok(routes.includes('const isInternal = (targetDomain && hostname.includes(targetDomain))'));
    assert.ok(routes.includes('const isReqInternal = (targetDomain && reqHost.includes(targetDomain))'));
    assert.ok(routes.includes('strategy: "same-domain"'));
    assert.ok(rawMain.includes('// context.config.circuitBreaker.isMicroMode = previousTotal < 50;'));
    assert.ok(!/^\s*context\.config\.circuitBreaker\.isMicroMode = previousTotal < 50;/m.test(main),
        'the isMicroMode line must stay commented');
});
