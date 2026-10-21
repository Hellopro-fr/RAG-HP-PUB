// A312 Final Review I1 (D7, décision user « tout couper ») — après le verdict `updateChecker.checkUrl`
// d'une requête bo_known, le handler s'arrête, dans la branche française comme dans la non française.
// Assertions sur le texte source : routes.ts (handler Crawlee) n'est pas exécutable par le runner —
// même méthode que routes.boKnown.test.ts.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

const raw = fs.readFileSync(path.join(import.meta.dirname, '..', 'routes.ts'), 'utf-8');
// Commentaires pleine ligne blanchis à longueur égale : un commentaire qui cite un littéral
// ne peut ni satisfaire ni casser une position.
const src = raw.replace(/^[ \t]*\/\/.*$/gm, (m) => ' '.repeat(m.length));

const CALL = 'await context.updateChecker.checkUrl(';
const GUARD = /if \(source === BO_KNOWN_SOURCE\) \{\s*return;\s*\}/g;

// Fin de l'appel `checkUrl` (update mode) dont les arguments portent `argMarker`.
function verdictEnd(argMarker: string): number {
    const hits: number[] = [];
    for (let i = src.indexOf(CALL); i !== -1; i = src.indexOf(CALL, i + 1)) {
        const end = src.indexOf(');', i);
        if (src.slice(i, end).includes(argMarker)) hits.push(end);
    }
    assert.equal(hits.length, 1, `exactly one update-mode checkUrl call carrying "${argMarker}"`);
    return hits[0];
}

function assertGuardBefore(argMarker: string, sideEffects: string[]) {
    const after = verdictEnd(argMarker);
    const positions = sideEffects.map((s) => {
        const p = src.indexOf(s, after);
        assert.notEqual(p, -1, `side effect "${s}" must still follow the verdict`);
        return p;
    });
    const firstSideEffect = Math.min(...positions);
    GUARD.lastIndex = after;
    const g = GUARD.exec(src);
    assert.ok(g, 'a bo_known early return must follow the verdict');
    assert.ok(
        g.index < firstSideEffect,
        `the bo_known early return (at ${g.index}) must precede the first side effect (at ${firstSideEffect})`,
    );
}

test('I1 French branch: bo_known returns after its verdict, before facets, routerDefaultHandler and enqueueLinks', () => {
    assertGuardBefore('true // Page is French', [
        'const facetUrl =',
        'await routerDefaultHandler(',
        'await enqueueLinks({',
    ]);
});

test('I1 non-French branch: bo_known returns after its verdict, before the nfr- dataset and its tryClaim(url)', () => {
    assertGuardBefore('false // NOT French', [
        'Dataset.open("nfr-"',
        'context.pushedSet.tryClaim(url)',
    ]);
});

test('I1: exactly two bo_known early returns in routes.ts (one per update-mode verdict)', () => {
    assert.equal(src.match(GUARD)?.length ?? 0, 2);
});

// A312 Final Review fix 2 (spec D2, « Compteurs propres ») — avant son verdict, une requête bo_known
// ne laisse aucune trace native : ni `filtered_nonfr`, ni `verdict_unavailable` + sidecar, ni
// clôture de boucle de redirection. Garde lue sur l'instruction de l'effet et sur les en-têtes des
// blocs `{` qui l'englobent.
function guardText(p: number, text: string = src): string {
    let start = p;
    while (start > 0 && !';{}'.includes(text[start - 1])) start--;
    const parts = [text.slice(start, p)];
    let depth = 0;
    for (let i = p - 1; i >= 0; i--) {
        const c = text[i];
        if (c === '}') depth++;
        else if (c === '{') {
            if (depth > 0) { depth--; continue; }
            let h = i;
            while (h > 0 && !';{}'.includes(text[h - 1])) h--;
            parts.push(text.slice(h, i));
        }
    }
    return parts.join(' | ');
}

function only(needle: string, text: string = src): number {
    const p = text.indexOf(needle);
    assert.notEqual(p, -1, `effect "${needle}" must exist`);
    assert.equal(text.indexOf(needle, p + 1), -1, `effect "${needle}" must exist exactly once`);
    return p;
}

function assertNativeOnly(needle: string) {
    const g = guardText(only(needle));
    assert.match(g, /source !== BO_KNOWN_SOURCE/, `"${needle}" must be reachable only when source !== BO_KNOWN_SOURCE; guards: ${g}`);
}

function verdictUnavailableBranch(): [number, number] {
    const start = only('} else if (verdictUnavailable) {');
    const end = src.indexOf('} else {', start);
    assert.notEqual(end, -1, 'the not-French terminal else must follow the verdictUnavailable branch');
    return [start, end];
}

test('fix2 item 1: the not-French else increments filtered_nonfr only for native sources', () => {
    assertNativeOnly('increment("filtered_nonfr")');
});

test('fix2 item 2: verdictUnavailable increments verdict_unavailable and records the sidecar only for native sources', () => {
    const [start, end] = verdictUnavailableBranch();
    for (const needle of ['increment("verdict_unavailable")', 'recordUnjudgedUrls(']) {
        const p = only(needle);
        assert.ok(p > start && p < end, `"${needle}" must stay in the verdictUnavailable branch`);
        assertNativeOnly(needle);
    }
});

test('fix2 item 2: verdictUnavailable counts a bo_known request through updateChecker.recordBoKnownUnjudged()', () => {
    const [start, end] = verdictUnavailableBranch();
    const p = src.indexOf('recordBoKnownUnjudged(', start);
    assert.ok(p > start && p < end, 'the call must sit in the verdictUnavailable branch');
    const g = guardText(p);
    assert.match(g, /source === BO_KNOWN_SOURCE/, `the call must be guarded by source === BO_KNOWN_SOURCE; guards: ${g}`);
    assert.match(src.slice(p - 60, p), /await context\.updateChecker(\?)?\.$/, 'the call must be awaited on context.updateChecker');
});

test('fix2 item 3: the redirect loop closure marks loadedUrl known only for native sources', () => {
    assertNativeOnly('context.dedupManager.addUrl(request.loadedUrl)');
});

// A312 Final Review fix 3 (spec D2, décision user 2026-10-21) — avant son verdict, une requête bo_known
// redirigée hors domaine (O1) ou servie en non-HTML (O2) ne laisse aucune trace native et compte dans
// bo_known_errors via updateChecker.recordBoKnownUnjudged(). Lecture bornée à la tranche de la branche.
function branchSlice(startNeedle: string, endNeedle: string, text: string = src): [number, number] {
    const start = only(startNeedle, text);
    const end = text.indexOf(endNeedle, start);
    assert.notEqual(end, -1, `"${endNeedle}" must follow "${startNeedle}"`);
    return [start, end];
}

function offDomainSlice(): [number, number] {
    return branchSlice('if (!isInternal) {', 'let enqueueLinksExcludePath');
}

function nonHtmlSlice(): [number, number] {
    const [start, log] = branchSlice(
        "if (contentType && !contentType.includes('text/html')",
        'Skipping non-HTML response:',
    );
    const end = src.indexOf('return;', log);
    assert.notEqual(end, -1, 'the non-HTML guard must end with its return;');
    return [start, end];
}

function assertNativeOnlyIn([start, end]: [number, number], needle: string, text: string = src) {
    const hits: number[] = [];
    for (let p = text.indexOf(needle, start); p !== -1 && p < end; p = text.indexOf(needle, p + 1)) hits.push(p);
    assert.ok(hits.length > 0, `effect "${needle}" must still sit in the branch`);
    for (const p of hits) {
        const g = guardText(p, text);
        assert.match(g, /source !== BO_KNOWN_SOURCE/, `"${needle}" must be reachable only when source !== BO_KNOWN_SOURCE; guards: ${g}`);
    }
}

function assertBoKnownUnjudgedIn([start, end]: [number, number], text: string = src) {
    const p = text.indexOf('recordBoKnownUnjudged(', start);
    assert.ok(p !== -1 && p < end, 'the branch must count a bo_known request through recordBoKnownUnjudged()');
    const g = guardText(p, text);
    assert.match(g, /source === BO_KNOWN_SOURCE/, `the call must be guarded by source === BO_KNOWN_SOURCE; guards: ${g}`);
    assert.match(text.slice(p - 60, p), /await context\.updateChecker(\?)?\.$/, 'the call must be awaited on context.updateChecker');
}

test('fix3 item 1 (O1): an off-domain redirect feeds external_redirects and the breaker only for native sources', () => {
    const slice = offDomainSlice();
    for (const needle of [
        'context.crawlErrorMessage =',
        'increment("external_redirects")',
        'shouldTripExternalRedirectBreaker(',
        'context.stopReason =',
        'context.fatalExitCode = 7',
        'stopCrawler(crawler',
    ]) {
        assertNativeOnlyIn(slice, needle);
    }
});

test('fix3 item 1 (O1): an off-domain redirect of a bo_known request counts through recordBoKnownUnjudged()', () => {
    assertBoKnownUnjudgedIn(offDomainSlice());
});

test('fix3 item 2 (O2): a non-HTML response feeds filtered_pdf, the pdf- dataset and prefix learning only for native sources', () => {
    const slice = nonHtmlSlice();
    for (const needle of [
        'increment("filtered_pdf")',
        'pdfDatasetName(',
        'pdfDataset.pushData(',
        'onNonHtml(',
    ]) {
        assertNativeOnlyIn(slice, needle);
    }
});

test('fix3 item 2 (O2): a non-HTML response of a bo_known request counts through recordBoKnownUnjudged()', () => {
    assertBoKnownUnjudgedIn(nonHtmlSlice());
});

// A312 Final Review fix 4 (spec D2, décision user 2026-10-21 option a) — une réponse bloquée (classe
// `block`) d'une requête bo_known n'entre pas dans le ratio du mur de proxy (`blockedCount`), et le saut
// download/PDF de failedRequestHandler (functions.ts) ne laisse aucune trace native. Pas d'appel à
// recordBoKnownUnjudged() dans la branche `block` : la requête est relancée, son verdict vient de la
// classification finale (checkUrl → checkBoKnown) une fois les relances épuisées.
function blockSlice(): [number, number] {
    return branchSlice('} else if (statusClass === "block") {', '} else {');
}

test('fix4 item 1: a blocked response feeds blockedCount and the proxy wall only for native sources', () => {
    const slice = blockSlice();
    for (const needle of [
        'context.blockedCount =',
        'shouldTripProxyWall(',
        'context.stopReason =',
        'context.fatalExitCode = 8',
        'stopCrawler(crawler',
    ]) {
        assertNativeOnlyIn(slice, needle);
    }
    const [start, end] = slice;
    assert.equal(
        src.slice(start, end).includes('recordBoKnownUnjudged('),
        false,
        'the block branch must not count a bo_known request (its verdict comes once retries are exhausted)',
    );
});

// functions.ts n'est pas importable par le runner (skipDownload.handler.test.ts:6-9) : même lecture du
// texte source, commentaires pleine ligne blanchis (fichier CRLF : `.` et `$` s'arrêtent avant `\r`).
const fsrc = fs
    .readFileSync(path.join(import.meta.dirname, '..', 'functions.ts'), 'utf-8')
    .replace(/^[ \t]*\/\/.*$/gm, (m) => ' '.repeat(m.length));

function downloadSkipSlice(): [number, number] {
    return branchSlice('if (shouldSkipAsDownload(SKIP_DOWNLOADS, errorStr)) {', 'return;', fsrc);
}

test('fix4 item 2: the download/PDF skip feeds filtered_pdf and the pdf- dataset only for native sources', () => {
    const slice = downloadSkipSlice();
    for (const needle of ['increment("filtered_pdf")', 'pdfDatasetName(', 'pushData(']) {
        assertNativeOnlyIn(slice, needle, fsrc);
    }
});

test('fix4 item 2: the download/PDF skip of a bo_known request counts through recordBoKnownUnjudged()', () => {
    assertBoKnownUnjudgedIn(downloadSkipSlice(), fsrc);
});
