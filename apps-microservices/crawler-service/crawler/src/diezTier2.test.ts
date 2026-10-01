import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import os from "node:os";
import { context } from "./context.js";
import { baseUrlKey, recordTier2Sample, maybeCommitTier2, tier2Evidence, maybeDefaultAtCeiling } from "./diezTier2.js";
import { ContentExtractorError } from "./class/ContentExtractorClient.js";

const resetT2 = () => {
    context.diezTier2 = { active: true, buffer: new Map(), compared: 0, matches: 0, mismatches: 0, unusable: 0 };
    context.diezDecisionCommitted = false;
};

const resetCeiling = () => {
    context.diezDecisionCommitted = false;
    context.countDiez = 0;
    context.config.skipDiez = false;
    context.config.bypassDiez = false;
    context.config.breakLimit = true;
    context.diezClassification = { anchor: 0, spa: 0, ambiguous: 0, total: 0, samplesForTier2: [] };
};
const tmpStorage = () => fs.mkdtempSync(path.join(os.tmpdir(), "diez-ceiling-"));

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

test("maybeDefaultAtCeiling: below 95, no commit", () => {
    resetCeiling();
    context.countDiez = 94;
    const s = tmpStorage();
    maybeDefaultAtCeiling(s);
    assert.equal(context.diezDecisionCommitted, false);
    assert.equal(context.config.bypassDiez, false);
    assert.equal(context.config.breakLimit, true);
    fs.rmSync(s, { recursive: true, force: true });
});

test("maybeDefaultAtCeiling: at 95 with no decision, commits default bypassDiez + arms 5000 backstop", () => {
    resetCeiling();
    context.countDiez = 95;
    const s = tmpStorage();
    maybeDefaultAtCeiling(s);
    assert.equal(context.config.bypassDiez, true);
    assert.equal(context.config.breakLimit, false);
    assert.equal(context.diezDecisionCommitted, true);
    // durable record written with the default source
    const decision = JSON.parse(fs.readFileSync(path.join(s, "_diez_decision.json"), "utf-8"));
    assert.equal(decision.decision, "bypassDiez");
    assert.equal(decision.source, "default");
    fs.rmSync(s, { recursive: true, force: true });
});

test("maybeDefaultAtCeiling: no-op once a decision is already committed", () => {
    resetCeiling();
    context.countDiez = 150;
    context.diezDecisionCommitted = true; // e.g. tier-1 already committed skipDiez
    const s = tmpStorage();
    maybeDefaultAtCeiling(s);
    assert.equal(context.config.bypassDiez, false); // not flipped
    assert.equal(context.config.breakLimit, true);  // backstop not touched
    fs.rmSync(s, { recursive: true, force: true });
});
