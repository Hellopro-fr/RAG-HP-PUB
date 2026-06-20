import { test } from "node:test";
import assert from "node:assert/strict";
import { normalizeForCompare, shingleSet, jaccard, classifyPair } from "./contentSimilarity.js";

test("normalizeForCompare collapses whitespace + lowercases", () => {
    assert.equal(normalizeForCompare("  Hello   WORLD\n\tfoo "), "hello world foo");
});

test("jaccard is 1 for identical, low for unrelated", () => {
    const a = "the quick brown fox jumps over the lazy dog today";
    assert.equal(jaccard(shingleSet(a), shingleSet(a)), 1);
    const b = "completely different words with no overlap whatsoever here";
    assert.ok(jaccard(shingleSet(a), shingleSet(b)) < 0.1);
});

test("classifyPair dead-band", () => {
    assert.equal(classifyPair(0.95), "match");
    assert.equal(classifyPair(0.85), "match");
    assert.equal(classifyPair(0.2), "mismatch");
    assert.equal(classifyPair(0.7), "unusable");
});

test("dynamic noise (swapped reviews) stays a match", () => {
    // Realistic content-rich page: a large stable body dominates and only a few
    // review lines differ load-to-load. Set-based shingle Jaccard absorbs that
    // small delta (>= 0.85). NB: a tiny repeated body would collapse to very few
    // distinct shingles, over-weighting the noise — not representative of a real
    // product page (which is hundreds of distinct words).
    const main = Array.from({ length: 120 }, (_, i) => `word${i}`).join(" ");
    const a = main + " review alice five stars great tool";
    const b = main + " review carol three stars decent buy";
    assert.equal(classifyPair(jaccard(shingleSet(normalizeForCompare(a)), shingleSet(normalizeForCompare(b)))), "match");
});
