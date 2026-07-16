import { test } from 'node:test';
import assert from 'node:assert/strict';
import { BROWSER_KILL_PATTERN } from '../browserKill.js';

test('BROWSER_KILL_PATTERN contains all required engines (slashed form)', () => {
    const expected = ['/chrome', '/chromium', '/firefox', '/camoufox', '/playwright', '/headless_shell'];
    const tokens = BROWSER_KILL_PATTERN.split('|');
    for (const token of expected) {
        assert.ok(
            tokens.includes(token),
            `Pattern missing engine "${token}". Got: "${BROWSER_KILL_PATTERN}"`,
        );
    }
});

test('BROWSER_KILL_PATTERN has no unintended tokens (slashed form only)', () => {
    const allowed = new Set(['/chrome', '/chromium', '/firefox', '/camoufox', '/playwright', '/headless_shell']);
    for (const token of BROWSER_KILL_PATTERN.split('|')) {
        assert.ok(
            allowed.has(token),
            `Unexpected token "${token}" in pattern — could kill non-browser processes`,
        );
    }
});

test('pattern does NOT match Node argv strings containing engine names', () => {
    // Regression guard for the self-kill bug: Node's own argv contains
    // "--camoufox=True" but has NO leading "/" before "camoufox", so the
    // path-anchored pattern must not match.
    const nodeArgvSamples = [
        'node /app/crawler/dist/main.js --domain=atosafr.fr --camoufox=True --typecrawling=link',
        'node /app/crawler/dist/main.js --site=https://x --camoufox=False',
        'node /app/crawler/dist/main.js --domain=playwright-test.com --camoufox=True',
    ];
    const regex = new RegExp(BROWSER_KILL_PATTERN);
    for (const argv of nodeArgvSamples) {
        assert.equal(
            regex.test(argv),
            false,
            `pattern matched Node argv string — would cause self-kill at pre-flight: "${argv}"`,
        );
    }
});

test('pattern DOES match legitimate browser executable paths', () => {
    const legitimateTargets = [
        '/root/.cache/camoufox/playwright/firefox-bin --remote-debugging-port=12345',
        '/ms-playwright/chromium-1234/chrome-linux/chrome --no-sandbox --headless',
        '/ms-playwright/chromium-1234/chrome-linux/headless_shell --user-data-dir=/tmp/x',
        'node /app/node_modules/playwright/cli.js launch-server',
    ];
    const regex = new RegExp(BROWSER_KILL_PATTERN);
    for (const target of legitimateTargets) {
        assert.equal(
            regex.test(target),
            true,
            `pattern failed to match legitimate browser target: "${target}"`,
        );
    }
});
