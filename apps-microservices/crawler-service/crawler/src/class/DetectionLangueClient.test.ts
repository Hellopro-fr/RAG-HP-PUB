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

test('isTechnicalFailureMethod() splits on "+" — a technical part anywhere wins', () => {
    assert.equal(DetectionLangueClient.isTechnicalFailureMethod('challenge_page+variant_rescue'), true);
    assert.equal(DetectionLangueClient.isTechnicalFailureMethod('direct_match+langHtml+nlp_confirmed'), false);
    assert.equal(DetectionLangueClient.isTechnicalFailureMethod('langHtml+nlp_confirmed+variant_rescue'), false);
});
