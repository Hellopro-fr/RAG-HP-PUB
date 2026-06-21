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
