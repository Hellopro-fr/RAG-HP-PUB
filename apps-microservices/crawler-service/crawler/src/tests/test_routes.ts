// Tests for the post-detect decision rule used in routes.ts default handler.
//
// Note (C-3): the regional-exclusion gate cases that previously lived here have moved
// to `test_DetectionLangueClient.ts`. They now exercise the production helper
// `DetectionLangueClient.computeExcludedRegionalPaths` directly, eliminating the
// hand-mirrored loop that used to drift from routes.ts.
//
// Internal-page validation (Task 4): the internal-page branch in routes.ts reads
// only `detectResult.ok` to set `isEnqueuingLinks`. The URL fallback (`checkUrl`)
// that previously ran on a clean rejection has been removed — it let .fr-TLD pages
// with non-FR HTML lang (aera-sa.fr/de/...) leak into the main dataset. Forced HTML
// detect is authoritative; URL TLD signals cannot override it.
//
// The handler is coupled to Crawlee + Playwright contexts, so we mirror the minimal
// post-detect decision rule here. The rule is a single-line ternary, too trivial to
// extract to production. If routes.ts diverges from this rule, update the helper
// alongside.

interface DetectVerdict {
    ok: boolean;
}

function decideEnqueuingLinks(detectResult: DetectVerdict): boolean {
    let isEnqueuingLinks = false;
    if (detectResult.ok) {
        isEnqueuingLinks = true;
    }
    // No URL fallback. Removed in Task 4.
    return isEnqueuingLinks;
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

// Case 1: clean acceptance enqueues links.
{
    const decision = decideEnqueuingLinks({ ok: true });
    assertEqual(decision, true, "ok=true → isEnqueuingLinks=true");
}

// Case 2: clean rejection (e.g. aera-sa.fr/de/... HTML lang=\"de-DE\") does NOT enqueue.
// Pre-Task-4 the URL fallback would have flipped this to true via .fr TLD direct_match.
{
    const decision = decideEnqueuingLinks({ ok: false });
    assertEqual(decision, false, "ok=false → no URL fallback override (aera-sa.fr leak fix)");
}

console.log(`\ntest_routes (post-detect rule): ${passed} passed, ${failed} failed`);
if (failed > 0) process.exit(1);
