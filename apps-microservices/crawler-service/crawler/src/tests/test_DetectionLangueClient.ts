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

// --- isFrenchRegionalPathPrefix tests ---

function testIsFrenchRegionalPathPrefix() {
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
        const result = DetectionLangueClient.isFrenchRegionalPathPrefix(prefix);
        if (result === expected) {
            passed++;
        } else {
            console.error(`FAIL [${label}]: isFrenchRegionalPathPrefix("${prefix}") = ${result}, expected ${expected}`);
            failed++;
        }
    }

    console.log(`isFrenchRegionalPathPrefix: ${passed} passed, ${failed} failed`);
    if (failed > 0) process.exit(1);
}

testExtractPathPrefix();
testIsExcludedRegionalPath();
testIsFrenchRegionalPathPrefix();