import { context } from "../context.js";

function testExcludedRegionalPathsDefaultsToEmpty() {
    let passed = 0;
    let failed = 0;

    if (Array.isArray(context.excludedRegionalPaths) && context.excludedRegionalPaths.length === 0) {
        passed++;
    } else {
        console.error("FAIL: excludedRegionalPaths should default to empty array");
        failed++;
    }

    if (context.homepageReady === null) {
        passed++;
    } else {
        console.error("FAIL: homepageReady should default to null");
        failed++;
    }

    console.log(`\ncontext fields: ${passed} passed, ${failed} failed`);
    if (failed > 0) process.exit(1);
}

testExcludedRegionalPathsDefaultsToEmpty();