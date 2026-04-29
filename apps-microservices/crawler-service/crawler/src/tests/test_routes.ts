// Tests for the regional-exclusion gate used in routes.ts default handler.
// The handler itself is tightly coupled to Crawlee + Playwright contexts, so we
// reproduce the exact filter/dedup logic here against the same DetectionLangueClient
// helpers it calls. This locks the gate behavior (jaunin.com belt-and-braces):
//   - Only locale-shaped prefixes survive into context.excludedRegionalPaths.
//   - Content prefixes (e.g. /nos-realisations) returned by a malformed hreflang
//     declaration are rejected and never blanket-block a content section.

import { DetectionLangueClient } from "../class/DetectionLangueClient.js";

interface AlternativeUrl {
    url: string;
}

// Mirrors the loop body inside routes.ts (lines ~418-440) post-Task-3.
// Kept in sync with the production code path; if routes.ts diverges, update here too.
function computeExcludedRegionalPaths(
    winnerUrl: string,
    seedUrl: string,
    alternatives: AlternativeUrl[],
): { excluded: string[]; rejectedNonLocale: string[] } {
    const winnerPrefix = DetectionLangueClient.extractPathPrefix(winnerUrl);
    const seedPrefix = DetectionLangueClient.extractPathPrefix(seedUrl);

    const excluded: string[] = [];
    const rejectedNonLocale: string[] = [];

    for (const alt of alternatives) {
        const altPrefix = DetectionLangueClient.extractPathPrefix(alt.url);
        if (altPrefix && altPrefix !== winnerPrefix && altPrefix !== seedPrefix) {
            if (!DetectionLangueClient.isFrenchRegionalPathPrefix(altPrefix)) {
                rejectedNonLocale.push(altPrefix);
                continue;
            }
            if (!excluded.includes(altPrefix)) {
                excluded.push(altPrefix);
            }
        }
    }

    return { excluded, rejectedNonLocale };
}

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
    const result = computeExcludedRegionalPaths(
        "https://www.manitou.com/fr-FR",
        "https://www.manitou.com/fr-FR",
        [
            { url: "https://www.manitou.com/fr-BE/" },
            { url: "https://www.manitou.com/fr-CA" },
            { url: "https://www.manitou.com/en-GB/" },
        ],
    );
    assertEqual(result.excluded.sort(), ["/en-GB", "/fr-BE", "/fr-CA"], "clean hreflang excludes all locale alts");
    assertEqual(result.rejectedNonLocale, [], "clean hreflang rejects nothing");
}

// Case 2: jaunin.com-style malformed hreflang — content prefix must NOT enter excluded set.
{
    const result = computeExcludedRegionalPaths(
        "https://www.jaunin.com/",
        "https://www.jaunin.com/",
        [
            { url: "https://www.jaunin.com/nos-realisations" },
            { url: "https://www.jaunin.com/produits/" },
            { url: "https://www.jaunin.com/fr-CH/" },
        ],
    );
    assertEqual(result.excluded, ["/fr-CH"], "only locale alt enters excluded list");
    assertEqual(
        result.rejectedNonLocale.sort(),
        ["/nos-realisations", "/produits"],
        "content prefixes rejected by gate",
    );
}

// Case 3: winner and seed prefixes are skipped before the gate is consulted.
{
    const result = computeExcludedRegionalPaths(
        "https://www.manitou.com/fr-FR",
        "https://www.manitou.com/fr-FR",
        [
            { url: "https://www.manitou.com/fr-FR/" },
            { url: "https://www.manitou.com/fr-BE" },
        ],
    );
    assertEqual(result.excluded, ["/fr-BE"], "winner prefix is filtered out before gate");
}

console.log(`\ntest_routes (regional-exclusion gate): ${passed} passed, ${failed} failed`);
if (failed > 0) process.exit(1);
