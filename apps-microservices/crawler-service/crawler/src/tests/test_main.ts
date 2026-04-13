/**
 * Tests for two-phase seeding logic in main.ts
 *
 * Note: main.ts is a top-level orchestration script with heavy side effects
 * (CLI args, Redis, file system, Crawlee). Unit testing the seeding logic
 * directly is not practical without a major refactor to extract it.
 *
 * These tests verify the building blocks used by the two-phase seeding:
 * - homepageReady promise signal pattern
 * - DetectionLangueClient.isExcludedRegionalPath filtering
 */

import { context } from "../context.js";
import { DetectionLangueClient } from "../class/DetectionLangueClient.js";

function testHomepageReadySignalPattern() {
    let passed = 0;
    let failed = 0;

    // Test 1: homepageReady can be created and resolved
    let resolveHomepage: () => void;
    const homepagePromise = new Promise<void>((resolve) => { resolveHomepage = resolve; });
    context.homepageReady = { resolve: resolveHomepage!, promise: homepagePromise };

    if (context.homepageReady !== null && typeof context.homepageReady.resolve === 'function') {
        passed++;
    } else {
        console.error("FAIL: homepageReady should have a resolve function");
        failed++;
    }

    // Test 2: Resolving the promise completes it
    context.homepageReady.resolve();
    context.homepageReady.promise.then(() => {
        passed++;
        console.log(`  homepageReady signal: ${passed} passed, ${failed} failed`);
    });

    // Reset
    context.homepageReady = null;

    console.log(`testHomepageReadySignalPattern: ${passed} passed, ${failed} failed (1 async)`);
}

function testPhase2FilteringWithExcludedPaths() {
    let passed = 0;
    let failed = 0;

    const excluded = ["/en", "/de", "/es"];

    // URL matching an excluded path should be filtered
    if (DetectionLangueClient.isExcludedRegionalPath("https://example.com/en/page", excluded)) {
        passed++;
    } else {
        console.error("FAIL: /en/page should be excluded");
        failed++;
    }

    // URL not matching any excluded path should pass through
    if (!DetectionLangueClient.isExcludedRegionalPath("https://example.com/fr/page", excluded)) {
        passed++;
    } else {
        console.error("FAIL: /fr/page should NOT be excluded");
        failed++;
    }

    // Empty excluded list should never filter
    if (!DetectionLangueClient.isExcludedRegionalPath("https://example.com/en/page", [])) {
        passed++;
    } else {
        console.error("FAIL: empty excluded list should not filter anything");
        failed++;
    }

    console.log(`testPhase2FilteringWithExcludedPaths: ${passed} passed, ${failed} failed`);
}

// Run tests
testHomepageReadySignalPattern();
testPhase2FilteringWithExcludedPaths();
