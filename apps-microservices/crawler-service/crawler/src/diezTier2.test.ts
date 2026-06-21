import { test } from "node:test";
import assert from "node:assert/strict";
import { context } from "./context.js";
import { baseUrlKey, recordTier2Sample, maybeCommitTier2, tier2Evidence } from "./diezTier2.js";
import { ContentExtractorError } from "./class/ContentExtractorClient.js";

const resetT2 = () => {
    context.diezTier2 = { active: true, buffer: new Map(), compared: 0, matches: 0, mismatches: 0, unusable: 0 };
    context.diezDecisionCommitted = false;
};

// Fake client: returns the html verbatim as "cleaned text" so identical html → match.
const echoClient = { clean: async (h: string) => h } as any;

test("baseUrlKey strips the fragment", () => {
    assert.equal(baseUrlKey("https://x.fr/p#a"), "https://x.fr/p");
    assert.equal(baseUrlKey("https://x.fr/p#b"), "https://x.fr/p");
});

test("first variant buffers, second adjudicates (match) and frees", async () => {
    resetT2();
    const SAME = "same long page content ".repeat(30);
    await recordTier2Sample("https://x.fr/p#a", SAME, echoClient);
    assert.equal(context.diezTier2.buffer.size, 1);
    await recordTier2Sample("https://x.fr/p#b", SAME, echoClient);
    assert.equal(context.diezTier2.buffer.size, 0);
    assert.equal(context.diezTier2.compared, 1);
    assert.equal(context.diezTier2.matches, 1);
});

test("same variant re-arriving does not re-buffer or adjudicate", async () => {
    resetT2();
    await recordTier2Sample("https://x.fr/p#a", "content one", echoClient);
    assert.equal(context.diezTier2.buffer.size, 1);
    // Same frag seen again — no second variant, so no comparison and no extra buffer.
    await recordTier2Sample("https://x.fr/p#a", "content one revisited", echoClient);
    assert.equal(context.diezTier2.buffer.size, 1);
    assert.equal(context.diezTier2.compared, 0);
});

test("commit skipDiez on >=3 match-majority", async () => {
    resetT2();
    const SAME = "same long page content ".repeat(30);
    for (const b of ["p", "q", "r"]) {
        await recordTier2Sample(`https://x.fr/${b}#a`, SAME, echoClient);
        await recordTier2Sample(`https://x.fr/${b}#z`, SAME, echoClient);
    }
    assert.equal(context.diezTier2.compared, 3);
    assert.equal(maybeCommitTier2(), "skipDiez");
});

test("commit bypassDiez on mismatch-majority", async () => {
    resetT2();
    const A = "alpha ".repeat(40), B = "beta ".repeat(40);
    for (const b of ["p", "q", "r"]) {
        await recordTier2Sample(`https://x.fr/${b}#a`, A, echoClient);
        await recordTier2Sample(`https://x.fr/${b}#z`, B, echoClient);
    }
    assert.equal(maybeCommitTier2(), "bypassDiez");
});

test("/clean throw → unusable, no false vote", async () => {
    resetT2();
    const throwClient = { clean: async () => { throw new Error("500"); } } as any;
    await recordTier2Sample("https://x.fr/p#a", "x", throwClient);
    await recordTier2Sample("https://x.fr/p#b", "x", throwClient);
    assert.equal(context.diezTier2.unusable, 1);
    assert.equal(context.diezTier2.matches, 0);
    assert.equal(context.diezTier2.mismatches, 0);
    assert.deepEqual(tier2Evidence(), { compared: 1, matches: 0, mismatches: 0, unusable: 1 });
});

test("transient /clean error does not consume a comparison; buffer retained for retry", async () => {
    resetT2();
    const SAME = "same long page content ".repeat(10);
    const flakyClient = { clean: async () => { throw new ContentExtractorError(503, true); } } as any;

    await recordTier2Sample("https://x.fr/p#a", SAME, flakyClient);
    assert.equal(context.diezTier2.buffer.size, 1);

    // 2nd variant while the service is saturated (503) → no tally, buffer kept
    await recordTier2Sample("https://x.fr/p#b", SAME, flakyClient);
    assert.equal(context.diezTier2.compared, 0);
    assert.equal(context.diezTier2.buffer.size, 1);

    // service recovers; a later variant adjudicates against the retained buffer
    await recordTier2Sample("https://x.fr/p#c", SAME, echoClient);
    assert.equal(context.diezTier2.compared, 1);
    assert.equal(context.diezTier2.matches, 1);
    assert.equal(context.diezTier2.buffer.size, 0);
});
