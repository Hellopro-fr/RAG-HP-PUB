import { test } from "node:test";
import assert from "node:assert/strict";
import { classifyFragment, applyPerClassStrip, perClassEnabled, fingerprint } from "./diezClassify.js";

test("classifyFragment unchanged after move (spot-check)", () => {
    assert.equal(classifyFragment(""), "anchor");
    assert.equal(classifyFragment("section2"), "anchor");
    assert.equal(classifyFragment("mot-de-passe-oublier"), "anchor");
    assert.equal(classifyFragment("/produit/1"), "spa");
    assert.equal(classifyFragment("a&b=c"), "spa");
});

test("applyPerClassStrip: strip anchors (incl empty), keep spa/ambiguous, keep query", () => {
    assert.equal(applyPerClassStrip("https://x.fr/p#"), "https://x.fr/p");
    assert.equal(applyPerClassStrip("https://x.fr/p#section"), "https://x.fr/p");
    assert.equal(applyPerClassStrip("https://x.fr/p#mot-de-passe-oublier"), "https://x.fr/p");
    assert.equal(applyPerClassStrip("https://x.fr/p?a=1#section"), "https://x.fr/p?a=1");
    assert.equal(applyPerClassStrip("https://x.fr/p#/produit/1"), "https://x.fr/p#/produit/1");
    assert.equal(applyPerClassStrip("https://x.fr/p#a&b=c"), "https://x.fr/p#a&b=c");
    assert.equal(applyPerClassStrip("https://x.fr/p"), "https://x.fr/p");
});

test("perClassEnabled reads env at call time", () => {
    delete process.env.DIEZ_PERCLASS_ENABLED;
    assert.equal(perClassEnabled(), false);
    process.env.DIEZ_PERCLASS_ENABLED = "true";
    assert.equal(perClassEnabled(), true);
    delete process.env.DIEZ_PERCLASS_ENABLED;
});

test("fingerprint: identical content equal, whitespace-normalized", () => {
    assert.equal(fingerprint("hello world"), fingerprint("  hello   world\n"));
});
test("fingerprint: differing content differs", () => {
    assert.notEqual(fingerprint("product A specs 500w"), fingerprint("product B specs 800w"));
});
test("fingerprint: empty is stable", () => {
    assert.equal(fingerprint(""), fingerprint("   "));
});
