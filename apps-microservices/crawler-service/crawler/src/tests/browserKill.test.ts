import { test } from 'node:test';
import assert from 'node:assert/strict';
import { BROWSER_KILL_PATTERN } from '../browserKill.js';

test('BROWSER_KILL_PATTERN contains all required engines', () => {
    const expected = ['chrome', 'chromium', 'firefox', 'camoufox', 'playwright', 'headless_shell'];
    const tokens = BROWSER_KILL_PATTERN.split('|');
    for (const token of expected) {
        assert.ok(
            tokens.includes(token),
            `Pattern missing engine "${token}". Got: "${BROWSER_KILL_PATTERN}"`,
        );
    }
});

test('BROWSER_KILL_PATTERN has no unintended tokens', () => {
    const allowed = new Set(['chrome', 'chromium', 'firefox', 'camoufox', 'playwright', 'headless_shell']);
    for (const token of BROWSER_KILL_PATTERN.split('|')) {
        assert.ok(
            allowed.has(token),
            `Unexpected token "${token}" in pattern — could kill non-browser processes`,
        );
    }
});
