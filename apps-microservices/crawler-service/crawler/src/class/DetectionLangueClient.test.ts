import { test } from 'node:test';
import assert from 'node:assert/strict';
import { DetectionLangueClient } from './DetectionLangueClient.js';

function clientWithCapture(): { client: DetectionLangueClient; getBody: () => any } {
    const c = new DetectionLangueClient('http://test');
    let captured: any = null;
    // Replace the internal axios instance with a stub that records the POST body.
    (c as any).client = {
        post: async (_path: string, body: any) => {
            captured = body;
            return { data: { ok: true, method: 'langHtml', url: 'http://x' } };
        },
    };
    return { client: c, getBody: () => captured };
}

test('detect() sends validate_alternatives:false when validateAlternatives=false', async () => {
    const { client, getBody } = clientWithCapture();
    await client.detect('http://x', '<html></html>', { mode: 'complete', validateAlternatives: false });
    assert.equal(getBody().validate_alternatives, false);
});

test('detect() omits validate_alternatives when option not provided', async () => {
    const { client, getBody } = clientWithCapture();
    await client.detect('http://x', '<html></html>', { mode: 'complete' });
    assert.equal(getBody().validate_alternatives, undefined);
});

test('detect() sends validate_alternatives:true when validateAlternatives=true', async () => {
    const { client, getBody } = clientWithCapture();
    await client.detect('http://x', '<html></html>', { mode: 'complete', validateAlternatives: true });
    assert.equal(getBody().validate_alternatives, true);
});

test('isTechnicalFailureMethod() is true for every member of the closed set', () => {
    // admission_rejected is unreachable on the crawler's calls today (it always
    // sends html_content, bypassing admission) — pinned anyway, see the predicate.
    for (const m of ['challenge_page', 'error', 'fetch_empty_content', 'admission_rejected']) {
        assert.equal(DetectionLangueClient.isTechnicalFailureMethod(m), true, m);
    }
});

test('isTechnicalFailureMethod() is false for the BO DETECTION_LANGUAGE_VERDICTS allowlist', () => {
    // The three methods the BO treats as *judged* negative verdicts. Swallowing any
    // of them would stop the crawler filtering genuinely non-French sites — this is
    // the boundary between "detection broke" and "the site is not French".
    for (const m of ['Check_nok_v2', 'nlp_not_confirmed', 'nlp_override_tld_fr']) {
        assert.equal(DetectionLangueClient.isTechnicalFailureMethod(m), false, m);
    }
});

test('isTechnicalFailureMethod() is false for success methods', () => {
    for (const m of ['langHtml', 'direct_match', 'nlp_confirmed']) {
        assert.equal(DetectionLangueClient.isTechnicalFailureMethod(m), false, m);
    }
});

test('isTechnicalFailureMethod() is false for the technical methods left out of the set', () => {
    // Deliberately excluded (unreachable behind `if not html_was_provided`), and
    // http_error also guards against a substring match on "error".
    for (const m of ['http_error', 'http_error_transient', 'soft_404', 'fetch_failed']) {
        assert.equal(DetectionLangueClient.isTechnicalFailureMethod(m), false, m);
    }
});

test('extractPrimaryMethod() prefers an HTML method found anywhere in the "+"-split', () => {
    // Why the `primaryMethod === "pattern_match_query"` gate on the ?lang=fr capture
    // was dead code: the HTML method wins over position 0, so a session-i18n site that
    // also declares <html lang="fr"> never reduced to pattern_match_query.
    assert.equal(
        DetectionLangueClient.extractPrimaryMethod('pattern_match_query+langHtml+nlp_confirmed'),
        'langHtml',
    );
});

const LANG_FR = { key: 'lang', value: 'fr' };

test('stripInjectedLanguageParam() drops the "?" entirely when nothing else remains', () => {
    // The whole point: the URL must stop matching `url.includes("?")` in routes.ts,
    // or countQuestionMark still walks to the limitQuestionMark stop.
    assert.equal(
        DetectionLangueClient.stripInjectedLanguageParam('http://a.fr/index.php?lang=fr', LANG_FR),
        'http://a.fr/index.php',
    );
});

test('stripInjectedLanguageParam() keeps the other params when the URL has some', () => {
    assert.equal(
        DetectionLangueClient.stripInjectedLanguageParam('http://a.fr/p?id=3&lang=fr&page=2', LANG_FR),
        'http://a.fr/p?id=3&page=2',
    );
});

test('stripInjectedLanguageParam() leaves the site\'s OWN ?lang=de alone', () => {
    // Exact key AND value match. A different value is the site's parameter, so it
    // must still increment countQuestionMark and still reach the tier-1/tier-2 engines.
    assert.equal(
        DetectionLangueClient.stripInjectedLanguageParam('http://a.fr/p?lang=de', LANG_FR),
        'http://a.fr/p?lang=de',
    );
});

test('stripInjectedLanguageParam() is a no-op when no param was injected (null)', () => {
    assert.equal(
        DetectionLangueClient.stripInjectedLanguageParam('http://a.fr/p?id=3', null),
        'http://a.fr/p?id=3',
    );
});

test('stripInjectedLanguageParam() leaves a query-less URL byte-identical', () => {
    // Bare origin on purpose: `new URL(u).toString()` would append a "/". Nothing we
    // do not modify may be normalized — `url` is compared elsewhere as a raw string.
    assert.equal(
        DetectionLangueClient.stripInjectedLanguageParam('http://a.fr', LANG_FR),
        'http://a.fr',
    );
});

test('stripInjectedLanguageParam() keeps a URL whose query lacks the param', () => {
    assert.equal(
        DetectionLangueClient.stripInjectedLanguageParam('http://a.fr/p?id=3', LANG_FR),
        'http://a.fr/p?id=3',
    );
});

test('stripInjectedLanguageParam() returns an unparseable URL unchanged instead of throwing', () => {
    // Runs on every page — a throw here would take down the handler.
    assert.equal(
        DetectionLangueClient.stripInjectedLanguageParam('not a url?lang=fr', LANG_FR),
        'not a url?lang=fr',
    );
});

test('isTechnicalFailureMethod() splits on "+" — a technical part anywhere wins', () => {
    assert.equal(DetectionLangueClient.isTechnicalFailureMethod('challenge_page+variant_rescue'), true);
    assert.equal(DetectionLangueClient.isTechnicalFailureMethod('direct_match+langHtml+nlp_confirmed'), false);
    assert.equal(DetectionLangueClient.isTechnicalFailureMethod('langHtml+nlp_confirmed+variant_rescue'), false);
});
