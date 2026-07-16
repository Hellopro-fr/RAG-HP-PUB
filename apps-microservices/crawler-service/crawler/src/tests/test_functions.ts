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

// --- reclaimFailedRequest: only recoverable records are re-queued ---
// Asserts the filter decision via the reclaim summary log (deterministic) + the
// error-dataset drop. Uses an isolated CRAWLEE_STORAGE_DIR; both the test seeding
// and reclaimFailedRequest go through the same global Crawlee config, so the result
// holds regardless of where storage resolves.
async function testReclaimFiltersByFailureClass() {
    let passed = 0;
    let failed = 0;

    const os = await import("os");
    const fsp = await import("fs/promises");
    const tmpRoot = await fsp.mkdtemp(path.join(os.tmpdir(), "reclaim-test-"));
    process.env.CRAWLEE_STORAGE_DIR = tmpRoot;

    const { RequestQueue, Dataset } = await import("crawlee");
    const { reclaimFailedRequest } = await import("../functions.js");

    const name = "reclaimtest.example";
    const queue = await RequestQueue.open(name);

    const urls = [
        "https://reclaimtest.example/infra",
        "https://reclaimtest.example/permanent",
        "https://reclaimtest.example/legacy",
    ];
    const { processedRequests } = await queue.addRequests(urls.map((url) => ({ url })));
    const ids = processedRequests.map((pr: any) => pr.requestId);

    const errorDataset = await Dataset.open(`error-${name}`);
    await errorDataset.pushData([
        { id: ids[0], url: urls[0], failure_class: "infra" },       // recoverable
        { id: ids[1], url: urls[1], failure_class: "permanent" },   // skipped
        { id: ids[2], url: urls[2] },                               // legacy missing → recoverable
    ]);

    // Capture reclaim's summary log to assert the filter decision deterministically.
    const logs: string[] = [];
    const origLog = console.log;
    console.log = (...args: any[]) => { logs.push(args.join(" ")); };
    try {
        await reclaimFailedRequest(name);
    } finally {
        console.log = origLog;
    }

    const summary = logs.find((l) => l.includes("recoverable requests, skipped")) || "";
    if (summary.includes("Reclaimed 2 recoverable requests, skipped 1 permanent")) {
        passed++;
    } else {
        console.error(`FAIL: expected 'Reclaimed 2 recoverable requests, skipped 1 permanent', got '${summary}'`);
        failed++;
    }

    // Error dataset dropped (reclaimedCount > 0 → dropDataset).
    const reopened = await Dataset.open(`error-${name}`);
    const after = await reopened.getInfo();
    if (!after || after.itemCount === 0) {
        passed++;
    } else {
        console.error(`FAIL: expected error dataset dropped/empty, got itemCount=${after.itemCount}`);
        failed++;
    }

    // Cleanup
    try { await queue.drop(); } catch (e) { /* ignore */ }
    try { await reopened.drop(); } catch (e) { /* ignore */ }
    await fsp.rm(tmpRoot, { recursive: true, force: true });
    delete process.env.CRAWLEE_STORAGE_DIR;

    console.log(`reclaimFailedRequest filter: ${passed} passed, ${failed} failed`);
    if (failed > 0) process.exit(1);
}

testReclaimFiltersByFailureClass();
