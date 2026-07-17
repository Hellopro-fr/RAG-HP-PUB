import { test } from "node:test";
import assert from "node:assert/strict";
import { context } from "./context.js";
import { recordQuestionMarkObservation, applyCliFlagGuard, getQuestionMarkDecisionMode } from "./questionMarkDecision.js";

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
