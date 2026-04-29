import { DetectionLangueClient } from "../class/DetectionLangueClient.js";

// --- extractPathPrefix tests ---

function testExtractPathPrefix() {
    const cases: [string, string | null, string][] = [
        ["https://www.manitou.com/fr-FR", "/fr-FR", "regional path"],
        ["https://www.manitou.com/fr-FR/", "/fr-FR", "regional path with trailing slash"],
        ["https://www.manitou.com/fr-FR/products/123", "/fr-FR", "deep path"],
        ["https://www.manitou.com/fr/", "/fr", "generic french path"],
        ["https://www.manitou.com/fr-BE", "/fr-BE", "other region"],
        ["https://www.manitou.com/", null, "root path"],
        ["https://www.manitou.com", null, "no path"],
        ["not-a-url", null, "invalid URL"],
    ];

    let passed = 0;
    let failed = 0;

    for (const [url, expected, label] of cases) {
        const result = DetectionLangueClient.extractPathPrefix(url);
        if (result === expected) {
            passed++;
        } else {
            console.error(`FAIL [${label}]: extractPathPrefix("${url}") = "${result}", expected "${expected}"`);
            failed++;
        }
    }

    console.log(`\nextractPathPrefix: ${passed} passed, ${failed} failed`);
    if (failed > 0) process.exit(1);
}

// --- isExcludedRegionalPath tests ---

function testIsExcludedRegionalPath() {
    const excluded = ["/fr", "/fr-BE", "/fr-CA"];

    const cases: [string, boolean, string][] = [
        ["https://www.manitou.com/fr-BE/products", true, "excluded prefix with subpath"],
        ["https://www.manitou.com/fr-BE", true, "excluded prefix exact"],
        ["https://www.manitou.com/fr-BE/", true, "excluded prefix with trailing slash"],
        ["https://www.manitou.com/fr/home", true, "excluded generic /fr/"],
        ["https://www.manitou.com/fr-FR/products", false, "allowed path (not excluded)"],
        ["https://www.manitou.com/france/products", false, "partial match must not trigger"],
        ["https://www.manitou.com/fr-BEL/products", false, "/fr-BEL != /fr-BE"],
        ["https://www.manitou.com/", false, "root path"],
        ["https://www.manitou.com/products", false, "unrelated path"],
    ];

    const emptyExcluded: string[] = [];

    let passed = 0;
    let failed = 0;

    for (const [url, expected, label] of cases) {
        const result = DetectionLangueClient.isExcludedRegionalPath(url, excluded);
        if (result === expected) {
            passed++;
        } else {
            console.error(`FAIL [${label}]: isExcludedRegionalPath("${url}") = ${result}, expected ${expected}`);
            failed++;
        }
    }

    const emptyResult = DetectionLangueClient.isExcludedRegionalPath("https://www.manitou.com/fr-BE/x", emptyExcluded);
    if (emptyResult === false) {
        passed++;
    } else {
        console.error("FAIL [empty list]: should return false with empty exclusion list");
        failed++;
    }

    console.log(`isExcludedRegionalPath: ${passed} passed, ${failed} failed`);
    if (failed > 0) process.exit(1);
}

// --- isLocalePathPrefix tests ---
// Renamed from isFrenchRegionalPathPrefix (C-2): the helper guards SHAPE, not language.

function testIsLocalePathPrefix() {
    const cases: [string, boolean, string][] = [
        // Accepted shapes
        ["/fr", true, "generic /fr"],
        ["/fr/", true, "/fr with trailing slash"],
        ["/fr-FR", true, "regional /fr-FR"],
        ["/fr-FR/", true, "/fr-FR with trailing slash"],
        ["/fr_FR", true, "/fr_FR underscore"],
        ["/fr_FR/", true, "/fr_FR underscore with trailing slash"],
        ["/fr-be", true, "/fr-be lowercase region"],
        ["/FR-FR", true, "/FR-FR uppercase"],
        ["/en", true, "/en non-FR language"],
        ["/en-GB", true, "/en-GB"],
        ["/de-DE", true, "/de-DE"],
        ["/es", true, "/es"],
        ["/es-ES", true, "/es-ES"],
        // Rejected shapes
        ["/nos-realisations", false, "content path"],
        ["/produits", false, "content path"],
        ["/a-propos", false, "content path with hyphen"],
        ["/l-entreprise", false, "content path with hyphen"],
        ["/", false, "root only"],
        ["", false, "empty string"],
        ["/fr/extra", false, "/fr with extra segment"],
        ["/fr-FR/extra", false, "/fr-FR with extra segment"],
        ["fr-FR", false, "missing leading slash"],
        ["/123", false, "digits not letters"],
        ["/f", false, "single-letter language code"],
    ];

    let passed = 0;
    let failed = 0;

    for (const [prefix, expected, label] of cases) {
        const result = DetectionLangueClient.isLocalePathPrefix(prefix);
        if (result === expected) {
            passed++;
        } else {
            console.error(`FAIL [${label}]: isLocalePathPrefix("${prefix}") = ${result}, expected ${expected}`);
            failed++;
        }
    }

    console.log(`isLocalePathPrefix: ${passed} passed, ${failed} failed`);
    if (failed > 0) process.exit(1);
}

// --- computeExcludedRegionalPaths tests ---
// Production helper extracted from routes.ts loop body (C-3). Tests now exercise
// the real method directly instead of a hand-mirrored copy in test_routes.ts.

function testComputeExcludedRegionalPaths() {
    let passed = 0;
    let failed = 0;

    function assertEqual<T>(actual: T, expected: T, label: string) {
        const a = JSON.stringify(actual);
        const e = JSON.stringify(expected);
        if (a === e) {
            passed++;
        } else {
            console.error(`FAIL [${label}]: got ${a}, expected ${e}`);
            failed++;
        }
    }

    // Case 1: typical clean hreflang — locale-shaped alts pass the gate.
    {
        const result = DetectionLangueClient.computeExcludedRegionalPaths(
            [
                { url: "https://www.manitou.com/fr-BE/", method: "hreflang", reliability: "high", validated: true },
                { url: "https://www.manitou.com/fr-CA", method: "hreflang", reliability: "high", validated: true },
                { url: "https://www.manitou.com/en-GB/", method: "hreflang", reliability: "high", validated: true },
            ],
            "/fr-FR",
            "/fr-FR",
        );
        assertEqual(result.excluded.sort(), ["/en-GB", "/fr-BE", "/fr-CA"], "clean hreflang excludes all locale alts");
        assertEqual(result.rejected, [], "clean hreflang rejects nothing");
    }

    // Case 2: jaunin.com-style malformed hreflang — content prefix must NOT enter excluded set.
    {
        const result = DetectionLangueClient.computeExcludedRegionalPaths(
            [
                { url: "https://www.jaunin.com/nos-realisations", method: "hreflang", reliability: "high", validated: true },
                { url: "https://www.jaunin.com/produits/", method: "hreflang", reliability: "high", validated: true },
                { url: "https://www.jaunin.com/fr-CH/", method: "hreflang", reliability: "high", validated: true },
            ],
            null,
            null,
        );
        assertEqual(result.excluded, ["/fr-CH"], "only locale alt enters excluded list");
        assertEqual(
            result.rejected.map(r => r.prefix).sort(),
            ["/nos-realisations", "/produits"],
            "content prefixes rejected by gate",
        );
        assertEqual(
            result.rejected.map(r => r.sourceUrl).sort(),
            ["https://www.jaunin.com/nos-realisations", "https://www.jaunin.com/produits/"],
            "rejected entries carry source URL for logging",
        );
    }

    // Case 3: winner and seed prefixes are skipped before the gate is consulted.
    {
        const result = DetectionLangueClient.computeExcludedRegionalPaths(
            [
                { url: "https://www.manitou.com/fr-FR/", method: "hreflang", reliability: "high", validated: true },
                { url: "https://www.manitou.com/fr-BE", method: "hreflang", reliability: "high", validated: true },
            ],
            "/fr-FR",
            "/fr-FR",
        );
        assertEqual(result.excluded, ["/fr-BE"], "winner prefix is filtered out before gate");
    }

    // Case 4: dedup — same prefix appearing twice is added only once.
    {
        const result = DetectionLangueClient.computeExcludedRegionalPaths(
            [
                { url: "https://www.manitou.com/fr-BE/", method: "hreflang", reliability: "high", validated: true },
                { url: "https://www.manitou.com/fr-BE/products", method: "hreflang", reliability: "high", validated: true },
            ],
            "/fr-FR",
            null,
        );
        assertEqual(result.excluded, ["/fr-BE"], "duplicate alt prefixes are deduped");
    }

    // Case 5: alt URL whose path prefix cannot be extracted (root) is silently skipped.
    {
        const result = DetectionLangueClient.computeExcludedRegionalPaths(
            [
                { url: "https://www.manitou.com/", method: "hreflang", reliability: "high", validated: true },
                { url: "https://www.manitou.com/fr-BE", method: "hreflang", reliability: "high", validated: true },
            ],
            "/fr-FR",
            null,
        );
        assertEqual(result.excluded, ["/fr-BE"], "alt URLs with no extractable prefix are skipped");
        assertEqual(result.rejected, [], "skipped alts do not enter rejected list");
    }

    console.log(`computeExcludedRegionalPaths: ${passed} passed, ${failed} failed`);
    if (failed > 0) process.exit(1);
}

testExtractPathPrefix();
testIsExcludedRegionalPath();
testIsLocalePathPrefix();
testComputeExcludedRegionalPaths();
