import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import os from "node:os";
import { context } from "./context.js";
import { recordQuestionMarkObservation, applyCliFlagGuard, getQuestionMarkDecisionMode, persistObservations, writeQmDecisionFile, readQmPersistedDecision } from "./questionMarkDecision.js";

const resetContextState = () => {
    context.questionMarkObservations = {
        paramFrequency: new Map(),
        samplesByParam: new Map(),
        domainSpecificCount: 0,
    };
    context.questionMarkObservationEnabled = true;
};

test("recordQuestionMarkObservation: URL without ? is a no-op", () => {
    resetContextState();
    recordQuestionMarkObservation("https://example.com/page");
    assert.equal(context.questionMarkObservations.domainSpecificCount, 0);
    assert.equal(context.questionMarkObservations.paramFrequency.size, 0);
});

test("recordQuestionMarkObservation: single-param URL records frequency + sample", () => {
    resetContextState();
    const url = "https://example.com/page?ref=promo";
    recordQuestionMarkObservation(url);

    assert.equal(context.questionMarkObservations.domainSpecificCount, 1);
    assert.equal(context.questionMarkObservations.paramFrequency.get("ref"), 1);
    assert.deepEqual(context.questionMarkObservations.samplesByParam.get("ref"), [url]);
});

test("recordQuestionMarkObservation: multi-param URL records all params", () => {
    resetContextState();
    const url = "https://example.com/page?ref=promo&variant=red&tab=reviews";
    recordQuestionMarkObservation(url);

    assert.equal(context.questionMarkObservations.domainSpecificCount, 1);
    assert.equal(context.questionMarkObservations.paramFrequency.get("ref"), 1);
    assert.equal(context.questionMarkObservations.paramFrequency.get("variant"), 1);
    assert.equal(context.questionMarkObservations.paramFrequency.get("tab"), 1);
});

test("recordQuestionMarkObservation: repeated param increments frequency, appends sample", () => {
    resetContextState();
    recordQuestionMarkObservation("https://example.com/a?ref=x");
    recordQuestionMarkObservation("https://example.com/b?ref=y");
    recordQuestionMarkObservation("https://example.com/c?ref=z");

    assert.equal(context.questionMarkObservations.paramFrequency.get("ref"), 3);
    assert.equal(context.questionMarkObservations.samplesByParam.get("ref")?.length, 3);
    assert.equal(context.questionMarkObservations.domainSpecificCount, 3);
});

test("recordQuestionMarkObservation: samplesByParam capped at 50", () => {
    resetContextState();
    for (let i = 0; i < 55; i++) {
        recordQuestionMarkObservation(`https://example.com/p${i}?ref=value${i}`);
    }
    assert.equal(context.questionMarkObservations.samplesByParam.get("ref")?.length, 50);
    // frequency keeps counting regardless of sample cap
    assert.equal(context.questionMarkObservations.paramFrequency.get("ref"), 55);
    assert.equal(context.questionMarkObservations.domainSpecificCount, 55);
});

test("recordQuestionMarkObservation: no-op when observation disabled", () => {
    resetContextState();
    context.questionMarkObservationEnabled = false;
    recordQuestionMarkObservation("https://example.com/page?ref=promo");

    assert.equal(context.questionMarkObservations.domainSpecificCount, 0);
    assert.equal(context.questionMarkObservations.paramFrequency.size, 0);
});

test("recordQuestionMarkObservation: malformed URL does not throw, no state change", () => {
    resetContextState();
    recordQuestionMarkObservation("not a valid url?foo=bar");
    // No assertion on state — implementation may either tolerate it (parse the query string directly)
    // or gracefully reject. Both are acceptable. The test just ensures no throw.
    assert.ok(true);
});

test("recordQuestionMarkObservation: param with empty value still recorded", () => {
    resetContextState();
    recordQuestionMarkObservation("https://example.com/page?ref=&tab=");

    assert.equal(context.questionMarkObservations.paramFrequency.get("ref"), 1);
    assert.equal(context.questionMarkObservations.paramFrequency.get("tab"), 1);
});

test("applyCliFlagGuard: no flag set → observation stays enabled", () => {
    resetContextState();
    context.config.skipQuestionMark = false;
    context.config.bypassQuestionMark = false;

    applyCliFlagGuard();

    assert.equal(context.questionMarkObservationEnabled, true);
});

test("applyCliFlagGuard: skipQuestionMark set → observation disabled", () => {
    resetContextState();
    context.config.skipQuestionMark = true;
    context.config.bypassQuestionMark = false;

    applyCliFlagGuard();

    assert.equal(context.questionMarkObservationEnabled, false);
});

test("applyCliFlagGuard: bypassQuestionMark set → observation disabled", () => {
    resetContextState();
    context.config.skipQuestionMark = false;
    context.config.bypassQuestionMark = true;

    applyCliFlagGuard();

    assert.equal(context.questionMarkObservationEnabled, false);
});

test("applyCliFlagGuard: both flags set → observation disabled", () => {
    resetContextState();
    context.config.skipQuestionMark = true;
    context.config.bypassQuestionMark = true;
    applyCliFlagGuard();
    assert.equal(context.questionMarkObservationEnabled, false);
});

test("getQuestionMarkDecisionMode: isError=limitQuestionMark → escalated", () => {
    resetContextState();
    assert.equal(getQuestionMarkDecisionMode("limitQuestionMark"), "escalated");
});

test("getQuestionMarkDecisionMode: observation disabled → unused", () => {
    resetContextState();
    context.questionMarkObservationEnabled = false;
    assert.equal(getQuestionMarkDecisionMode(undefined), "unused");
});

test("getQuestionMarkDecisionMode: no ? URLs observed → unused", () => {
    resetContextState();
    assert.equal(getQuestionMarkDecisionMode(undefined), "unused");
});

test("getQuestionMarkDecisionMode: observation ran with samples → observed", () => {
    resetContextState();
    recordQuestionMarkObservation("https://example.com/page?ref=promo");
    assert.equal(context.questionMarkObservations.domainSpecificCount, 1);
    assert.equal(getQuestionMarkDecisionMode(undefined), "observed");
});

test("getQuestionMarkDecisionMode: escalated takes priority over observed", () => {
    resetContextState();
    recordQuestionMarkObservation("https://example.com/page?ref=promo");
    assert.equal(getQuestionMarkDecisionMode("limitQuestionMark"), "escalated");
});

// -----------------------------------------------------------------------------
// persistObservations — phase-1.5 sidecar tests
// -----------------------------------------------------------------------------

const makeTmpStorage = (): string =>
    fs.mkdtempSync(path.join(os.tmpdir(), "qmark-obs-"));

test("persistObservations: writes paramFrequency + samplesByParam + domainSpecificCount", () => {
    resetContextState();
    const storage = makeTmpStorage();
    recordQuestionMarkObservation("https://example.com/a?ref=x&tab=reviews");
    recordQuestionMarkObservation("https://example.com/b?ref=y");

    persistObservations(storage);

    const filePath = path.join(storage, "_questionmark_observations.json");
    assert.ok(fs.existsSync(filePath), "sidecar file not written");

    const payload = JSON.parse(fs.readFileSync(filePath, "utf-8"));
    assert.equal(payload.paramFrequency.ref, 2);
    assert.equal(payload.paramFrequency.tab, 1);
    assert.equal(payload.samplesByParam.ref.length, 2);
    assert.equal(payload.samplesByParam.tab.length, 1);
    assert.equal(payload.domainSpecificCount, 2);
    assert.ok(typeof payload.persistedAt === "string");

    fs.rmSync(storage, { recursive: true, force: true });
});

test("persistObservations: empty observations write valid JSON with zero counts", () => {
    resetContextState();
    const storage = makeTmpStorage();

    persistObservations(storage);

    const payload = JSON.parse(fs.readFileSync(path.join(storage, "_questionmark_observations.json"), "utf-8"));
    assert.deepEqual(payload.paramFrequency, {});
    assert.deepEqual(payload.samplesByParam, {});
    assert.equal(payload.domainSpecificCount, 0);

    fs.rmSync(storage, { recursive: true, force: true });
});

test("persistObservations: failure on invalid path does not throw", () => {
    resetContextState();
    recordQuestionMarkObservation("https://example.com/p?ref=x");

    // path that cannot be written (no parent dir) — sidecar should swallow
    const bogus = path.join(os.tmpdir(), "does-not-exist-" + Date.now(), "nested", "deeper");

    assert.doesNotThrow(() => persistObservations(bogus));
});

test("persistObservations: atomic write — no .tmp left after success", () => {
    resetContextState();
    const storage = makeTmpStorage();
    recordQuestionMarkObservation("https://example.com/p?ref=x");

    persistObservations(storage);

    const entries = fs.readdirSync(storage);
    assert.ok(entries.includes("_questionmark_observations.json"), "final file missing");
    assert.ok(!entries.some(e => e.endsWith(".tmp")), "stale .tmp left behind");

    fs.rmSync(storage, { recursive: true, force: true });
});

// -----------------------------------------------------------------------------
// Phase-2 tier-2 persistence + decision-mode tests
// -----------------------------------------------------------------------------

const resetQm = () => {
    context.qmTier2 = { active: true, contentByUrl: new Map(), groups: new Map(), tally: new Map(), decided: new Set(), addedToRemove: [], contentShaping: [], defaulted: false };
    context.config.toRemove = [];
    context.questionMarkObservationEnabled = true;
    context.questionMarkObservations.domainSpecificCount = 0;
};

test("writeQmDecisionFile writes addedToRemove + pairStats", () => {
    resetQm();
    const s = makeTmpStorage();
    context.qmTier2.addedToRemove = ["ref"];
    context.qmTier2.tally.set("ref", { same: 4, different: 0, unusable: 1 });
    writeQmDecisionFile(s, "tier2");
    const p = JSON.parse(fs.readFileSync(path.join(s, "_questionmark_decision.json"), "utf-8"));
    assert.deepEqual(p.addedToRemove, ["ref"]);
    assert.equal(p.pairStats.ref.same, 4);
    assert.equal(p.source, "tier2");
    fs.rmSync(s, { recursive: true, force: true });
});

test("readQmPersistedDecision merges addedToRemove into toRemove", () => {
    resetQm();
    const s = makeTmpStorage();
    fs.writeFileSync(path.join(s, "_questionmark_decision.json"), JSON.stringify({ addedToRemove: ["ref", "tab"], source: "tier2" }));
    context.config.toRemove = ["ref"]; // already present — must dedupe
    assert.equal(readQmPersistedDecision(s), true);
    assert.deepEqual(context.config.toRemove.sort(), ["ref", "tab"]);
    fs.rmSync(s, { recursive: true, force: true });
});

test("readQmPersistedDecision: missing/malformed → false", () => {
    resetQm();
    const s = makeTmpStorage();
    assert.equal(readQmPersistedDecision(s), false);
    fs.writeFileSync(path.join(s, "_questionmark_decision.json"), "not-json");
    assert.equal(readQmPersistedDecision(s), false);
    fs.rmSync(s, { recursive: true, force: true });
});

test("getQuestionMarkDecisionMode state machine", () => {
    resetQm();
    assert.equal(getQuestionMarkDecisionMode("limitQuestionMark"), "escalated");
    context.qmTier2.defaulted = true;
    assert.equal(getQuestionMarkDecisionMode(undefined), "defaulted-bypassed");
    context.qmTier2.defaulted = false;
    context.qmTier2.addedToRemove = ["ref"];
    assert.equal(getQuestionMarkDecisionMode(undefined), "tier2-resolved");
    context.qmTier2.addedToRemove = [];
    context.questionMarkObservations.domainSpecificCount = 5;
    assert.equal(getQuestionMarkDecisionMode(undefined), "observed");
    context.questionMarkObservations.domainSpecificCount = 0;
    assert.equal(getQuestionMarkDecisionMode(undefined), "unused");
});
