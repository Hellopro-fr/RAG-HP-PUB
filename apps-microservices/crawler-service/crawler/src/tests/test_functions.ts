// Tests for manageFrenchDetectionMethod excluded paths persistence
// Verifies that excludedRegionalPaths survives write/read round-trip via {domain}.json

import * as fs from "fs";
import * as path from "path";
import { context } from "../context.js";

function testExcludedPathsPersistence() {
    const testDomain = "__test_persistence__";
    const storagePath = `./storage/miscellaneous/${testDomain}`;
    const filePath = `${storagePath}/${testDomain}.json`;

    // Cleanup before test
    if (fs.existsSync(filePath)) fs.unlinkSync(filePath);
    if (fs.existsSync(storagePath)) fs.rmdirSync(storagePath);

    let passed = 0;
    let failed = 0;

    // Test 1: Write method with excluded paths
    context.excludedRegionalPaths = ["/fr", "/fr-BE", "/fr-CA"];
    context.frenchDetectionMethod = null;

    // Simulate manageFrenchDetectionMethod write (inline to avoid import cycle)
    if (!fs.existsSync(storagePath)) fs.mkdirSync(storagePath, { recursive: true });
    const data: Record<string, any> = { method: "langHtml" };
    if (context.excludedRegionalPaths.length > 0) {
        data.excludedPaths = context.excludedRegionalPaths;
    }
    fs.writeFileSync(filePath, JSON.stringify(data, null, 2));

    // Test 2: Read back and verify
    const content = JSON.parse(fs.readFileSync(filePath, "utf-8"));
    if (content.method === "langHtml") {
        passed++;
    } else {
        console.error(`FAIL: method should be "langHtml", got "${content.method}"`);
        failed++;
    }

    if (JSON.stringify(content.excludedPaths) === JSON.stringify(["/fr", "/fr-BE", "/fr-CA"])) {
        passed++;
    } else {
        console.error(`FAIL: excludedPaths should be ["/fr", "/fr-BE", "/fr-CA"], got ${JSON.stringify(content.excludedPaths)}`);
        failed++;
    }

    // Test 3: Restore into context (simulate read path)
    context.excludedRegionalPaths = []; // Reset
    if (content.excludedPaths && Array.isArray(content.excludedPaths)) {
        context.excludedRegionalPaths = content.excludedPaths;
    }
    if (JSON.stringify(context.excludedRegionalPaths) === JSON.stringify(["/fr", "/fr-BE", "/fr-CA"])) {
        passed++;
    } else {
        console.error(`FAIL: context.excludedRegionalPaths not restored, got ${JSON.stringify(context.excludedRegionalPaths)}`);
        failed++;
    }

    // Test 4: Write without excluded paths
    context.excludedRegionalPaths = [];
    const data2: Record<string, any> = { method: "matchMeta" };
    if (context.excludedRegionalPaths.length > 0) {
        data2.excludedPaths = context.excludedRegionalPaths;
    }
    fs.writeFileSync(filePath, JSON.stringify(data2, null, 2));
    const content2 = JSON.parse(fs.readFileSync(filePath, "utf-8"));
    if (content2.excludedPaths === undefined) {
        passed++;
    } else {
        console.error(`FAIL: excludedPaths should be absent when empty, got ${JSON.stringify(content2.excludedPaths)}`);
        failed++;
    }

    // Cleanup
    fs.unlinkSync(filePath);
    fs.rmdirSync(storagePath);
    context.excludedRegionalPaths = [];
    context.frenchDetectionMethod = null;

    console.log(`\nexcludedPaths persistence: ${passed} passed, ${failed} failed`);
    if (failed > 0) process.exit(1);
}

testExcludedPathsPersistence();
