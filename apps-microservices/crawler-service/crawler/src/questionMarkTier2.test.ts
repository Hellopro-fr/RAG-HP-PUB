import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import os from "node:os";
import { context } from "./context.js";
import { baseKeyWithout, recordQmTier2Sample, maybeCommitParam, maybeDefaultAtCeiling } from "./questionMarkTier2.js";
import { ContentExtractorError } from "./class/ContentExtractorClient.js";

const echo = { clean: async (h: string) => h } as any; // identical html -> match
const resetQm = () => {
    context.qmTier2 = { active: true, contentByUrl: new Map(), groups: new Map(), tally: new Map(), decided: new Set(), addedToRemove: [], contentShaping: [], defaulted: false };
    context.config.toRemove = [];
    context.config.toKeep = [];
    context.config.bypassQuestionMark = false;
    context.config.breakLimit = true;
    context.countQuestionMark = 0;
    context.questionMarkObservations.paramFrequency = new Map([["ref", 10], ["page", 10]]);
};

test("baseKeyWithout drops the param", () => {
    assert.equal(baseKeyWithout("https://x.fr/a?ref=1&z=2", "ref"), "https://x.fr/a?z=2");
});

test("two ref values, same content -> same tally", async () => {
    resetQm();
    const SAME = "same long page content ".repeat(30);
    await recordQmTier2Sample("https://x.fr/a?ref=1&z=2", SAME, echo);
    await recordQmTier2Sample("https://x.fr/a?ref=9&z=2", SAME, echo);
    assert.equal(context.qmTier2.tally.get("ref")!.same, 1);
});

test("strategy B: value-vs-absent pairs and adjudicates", async () => {
    resetQm();
    const SAME = "same long page content ".repeat(30);
    await recordQmTier2Sample("https://x.fr/a?ref=1&z=2", SAME, echo); // ref present
    await recordQmTier2Sample("https://x.fr/a?z=2", SAME, echo);       // ref absent → same base key
    assert.equal(context.qmTier2.tally.get("ref")!.same, 1);
});

test("commit ref to toRemove on >=3 same-majority", async () => {
    resetQm();
    const SAME = "same long page content ".repeat(30);
    for (const base of ["a", "b", "c"]) {
        await recordQmTier2Sample(`https://x.fr/${base}?ref=1&z=2`, SAME, echo);
        await recordQmTier2Sample(`https://x.fr/${base}?ref=9&z=2`, SAME, echo);
    }
    assert.equal(maybeCommitParam("ref"), true);
});

test("page differs -> content-shaping, not committed", async () => {
    resetQm();
    for (const base of ["a", "b", "c"]) {
        await recordQmTier2Sample(`https://x.fr/${base}?page=1`, "alpha ".repeat(40), echo);
        await recordQmTier2Sample(`https://x.fr/${base}?page=2`, "beta ".repeat(40), echo);
    }
    assert.equal(maybeCommitParam("page"), false);
    assert.ok(context.qmTier2.contentShaping.includes("page"));
});

test("transient /clean error does not tally; group retained for retry", async () => {
    resetQm();
    const SAME = "same long page content ".repeat(30);
    const flaky = { clean: async () => { throw new ContentExtractorError(503, true); } } as any;
    await recordQmTier2Sample("https://x.fr/a?ref=1&z=2", SAME, flaky);
    await recordQmTier2Sample("https://x.fr/a?ref=9&z=2", SAME, flaky); // adjudication hits 503 -> error
    assert.equal(context.qmTier2.tally.get("ref"), undefined); // no tally on transient
    // service recovers: a later ref variant adjudicates against the retained group
    await recordQmTier2Sample("https://x.fr/a?ref=5&z=2", SAME, echo);
    assert.equal(context.qmTier2.tally.get("ref")!.same, 1);
});

test("default at ceiling: bypass + 5000 backstop, once", () => {
    resetQm();
    context.countQuestionMark = 95;
    const s = fs.mkdtempSync(path.join(os.tmpdir(), "qm-d-"));
    maybeDefaultAtCeiling(s);
    assert.equal(context.config.bypassQuestionMark, true);
    assert.equal(context.config.breakLimit, false);
    assert.equal(context.qmTier2.defaulted, true);
    fs.rmSync(s, { recursive: true, force: true });
});

// B1 raw-HTML veto tests.
// /clean returns the SAME chrome text for every page -> /clean always "matches".
const chromeClient = { clean: async () => "shared site chrome menu footer legal notice cart" } as any;
// MODERATE raw similarity: a large non-repeating shared body (-> many distinct trigrams)
// + a small unique tail per variant. Raw jaccard lands ~0.81 — strictly between the two
// thresholds the tests drive (0.99 vs 0.30), so they probe the CALL-TIME env on opposite
// sides. With the old const-at-import bug these two could not both pass: a regression guard.
const RAW_COMMON =
    "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi omicron pi rho sigma tau upsilon phi chi psi omega one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty";
const RAW_A = RAW_COMMON + " uniquealphapayload red green blue yellow";
const RAW_B = RAW_COMMON + " uniquebetapayload purple orange pink cyan";

test("B1 veto: /clean-match but raw HTML differs -> NOT counted same", async () => {
    process.env.QM_RAW_SAME_SIM = "0.99"; // raw ~0.81 < 0.99 -> vetoed
    resetQm();
    context.questionMarkObservations.paramFrequency = new Map([["q", 10]]);
    for (const b of ["a", "b", "c"]) {
        await recordQmTier2Sample(`https://x.fr/${b}?q=AAA`, RAW_A, chromeClient);
        await recordQmTier2Sample(`https://x.fr/${b}?q=BBB`, RAW_B, chromeClient);
    }
    const tally = context.qmTier2.tally.get("q");
    assert.ok(tally && tally.same === 0, `expected 0 same (vetoed), got ${JSON.stringify(tally)}`);
    assert.equal(maybeCommitParam("q"), false); // not committed -> q kept
    delete process.env.QM_RAW_SAME_SIM;
});

test("B1 pass: /clean-match AND raw similar -> same (commits)", async () => {
    process.env.QM_RAW_SAME_SIM = "0.30"; // SAME fixtures, raw ~0.81 >= 0.30 -> NOT vetoed
    resetQm();
    context.questionMarkObservations.paramFrequency = new Map([["ref", 10]]);
    for (const b of ["a", "b", "c"]) {
        await recordQmTier2Sample(`https://x.fr/${b}?ref=1`, RAW_A, chromeClient);
        await recordQmTier2Sample(`https://x.fr/${b}?ref=9`, RAW_B, chromeClient);
    }
    assert.equal(context.qmTier2.tally.get("ref")!.same, 3);
    assert.equal(maybeCommitParam("ref"), true);
    delete process.env.QM_RAW_SAME_SIM;
});

// Language-param exclusion. `candidateParams` is not exported, so this drives it the way the
// tests above do — through `recordQmTier2Sample`, seeding `paramFrequency` and reading back
// `context.qmTier2.tally`. Exporting the function just to test it would test a different
// surface than the one routes.ts calls.
test("language params are never tier-2 candidates; a control param still is", async () => {
    resetQm();
    const SAME = "same long page content ".repeat(30);
    // Every language key + two case variants, all ranked ABOVE the control, so without the
    // guard they would be the top candidates. Values differ (de vs fr) with identical content
    // => a same-majority verdict, i.e. exactly the commit-to-toRemove path.
    const langKeys = ["lang", "locale", "language", "hl", "LANG", "Locale"];
    context.questionMarkObservations.paramFrequency = new Map<string, number>([
        ...langKeys.map((k) => [k, 99] as [string, number]),
        ["ref", 1],
    ]);
    for (const k of langKeys) {
        for (const b of ["a", "b", "c"]) {
            await recordQmTier2Sample(`https://x.fr/${k}/${b}?${k}=de`, SAME, echo);
            await recordQmTier2Sample(`https://x.fr/${k}/${b}?${k}=fr`, SAME, echo);
        }
    }
    for (const k of langKeys) {
        assert.equal(context.qmTier2.tally.get(k), undefined, `${k} must never be sampled`);
        assert.equal(maybeCommitParam(k), false, `${k} must never commit`);
    }
    // Control, same run: a non-language param IS sampled and DOES commit. Without it this test
    // would pass on an inert module, on an exclusion that swallows everything, or on a
    // maybeCommitParam stubbed to a constant false.
    for (const b of ["d", "e", "f"]) {
        await recordQmTier2Sample(`https://x.fr/${b}?ref=1`, SAME, echo);
        await recordQmTier2Sample(`https://x.fr/${b}?ref=9`, SAME, echo);
    }
    assert.equal(context.qmTier2.tally.get("ref")!.same, 3);
    assert.equal(maybeCommitParam("ref"), true);
});
