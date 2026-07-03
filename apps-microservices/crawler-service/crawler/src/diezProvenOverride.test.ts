import { test } from "node:test";
import assert from "node:assert/strict";
import { isProvenDiezStrip } from "./diezClassify.js";

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
