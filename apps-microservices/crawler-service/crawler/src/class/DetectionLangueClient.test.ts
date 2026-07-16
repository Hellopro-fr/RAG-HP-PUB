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
