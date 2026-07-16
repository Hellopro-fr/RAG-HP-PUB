import { test } from 'node:test';
import assert from 'node:assert/strict';

import { CRAWLER_BROWSER_LOCALE, buildCamoufoxLaunchInput } from './camoufoxLaunchInput.js';

// Regression guard for the cryolor.com class of bug.
//
// Sites with client-side language negotiation (e.g. Drupal's
// `browser_language_detection` module) read `navigator.language` in the browser
// and redirect a /fr page to the default-language root when it is not French:
//   o = navigator.language.substring(0,2); if (o !== pageLang) location.href = redirections[o];
// The crawler's Camoufox browser must therefore advertise a French locale so
// `navigator.language.substring(0,2) === 'fr'` and the seeded French URL is kept.
// Mirrors api-detection-langue-fr's scraper (locale 'fr-FR').

test('CRAWLER_BROWSER_LOCALE advertises French to navigator.language', () => {
    assert.equal(CRAWLER_BROWSER_LOCALE, 'fr-FR');
    // The redirect script keys off the first two chars of navigator.language.
    assert.equal(CRAWLER_BROWSER_LOCALE.substring(0, 2), 'fr');
});

test('buildCamoufoxLaunchInput always pins the French locale', () => {
    const input = buildCamoufoxLaunchInput(true);
    assert.equal(input.locale, 'fr-FR');
    assert.equal(input.headless, true);
});

test('buildCamoufoxLaunchInput preserves the headless flag', () => {
    assert.equal(buildCamoufoxLaunchInput(false).headless, false);
    assert.equal(buildCamoufoxLaunchInput(false).locale, 'fr-FR');
});
