import { test } from "node:test";
import assert from "node:assert/strict";
import { isProvenDiezStrip, provenOverrideMinCompared } from "./diezClassify.js";

test("isProvenDiezStrip: true only when enabled + committed + skipDiez + tier2", () => {
    assert.equal(isProvenDiezStrip(true, true, true, "tier2"), true);
});

test("isProvenDiezStrip: false when any condition missing", () => {
    assert.equal(isProvenDiezStrip(false, true, true, "tier2"), false, "flag off");
    assert.equal(isProvenDiezStrip(true, false, true, "tier2"), false, "not committed");
    assert.equal(isProvenDiezStrip(true, true, false, "tier2"), false, "skipDiez false");
    assert.equal(isProvenDiezStrip(true, true, true, "tier1"), false, "tier1 not proven");
    assert.equal(isProvenDiezStrip(true, true, true, "default"), false, "default not proven");
});

test("isProvenDiezStrip: min-compared gate", () => {
    assert.equal(isProvenDiezStrip(true, true, true, "tier2", 3, 3), true, "compared == min arms");
    assert.equal(isProvenDiezStrip(true, true, true, "tier2", 10, 8), true, "compared > min arms");
    assert.equal(isProvenDiezStrip(true, true, true, "tier2", 3, 8), false, "compared < min disarms");
    assert.equal(isProvenDiezStrip(true, true, true, "tier2", null, 8), true, "unknown evidence keeps pre-knob behavior");
    assert.equal(isProvenDiezStrip(true, true, true, "tier1", 100, 3), false, "gate never promotes a non-tier2 source");
});

test("provenOverrideMinCompared: env parsing with safe default 3", () => {
    const prev = process.env.DIEZ_PROVEN_OVERRIDE_MIN_COMPARED;
    try {
        delete process.env.DIEZ_PROVEN_OVERRIDE_MIN_COMPARED;
        assert.equal(provenOverrideMinCompared(), 3, "absent -> 3");
        process.env.DIEZ_PROVEN_OVERRIDE_MIN_COMPARED = "8";
        assert.equal(provenOverrideMinCompared(), 8);
        process.env.DIEZ_PROVEN_OVERRIDE_MIN_COMPARED = "0";
        assert.equal(provenOverrideMinCompared(), 3, "non-positive -> 3");
        process.env.DIEZ_PROVEN_OVERRIDE_MIN_COMPARED = "abc";
        assert.equal(provenOverrideMinCompared(), 3, "garbage -> 3");
    } finally {
        if (prev === undefined) delete process.env.DIEZ_PROVEN_OVERRIDE_MIN_COMPARED;
        else process.env.DIEZ_PROVEN_OVERRIDE_MIN_COMPARED = prev;
    }
});
