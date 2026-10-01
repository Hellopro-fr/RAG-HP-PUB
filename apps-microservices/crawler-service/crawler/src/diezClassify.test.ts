import { test } from "node:test";
import assert from "node:assert/strict";
import { classifyFragment, applyPerClassStrip, perClassEnabled, fingerprint, stripActionAnchor, actionAnchorStripEnabled } from "./diezClassify.js";

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

const aaBase = "https://www.capsa-container.com/realisations/page/5/";

test("stripActionAnchor: strips elementor off_canvas toggle (encoded)", () => {
    const url = aaBase + "#elementor-action%3Aaction%3Doff_canvas%3Atoggle%26settings%3DeyJpZCI6IjAwNTljYmEifQ%3D%3D";
    assert.equal(stripActionAnchor(url), aaBase);
});
test("stripActionAnchor: strips popup:open (encoded)", () => {
    const url = aaBase + "#elementor-action%3Aaction%3Dpopup%3Aopen%26settings%3DeyJpZCI6IjYwODcifQ%3D%3D";
    assert.equal(stripActionAnchor(url), aaBase);
});
test("stripActionAnchor: strips an already-decoded action-anchor", () => {
    assert.equal(stripActionAnchor(aaBase + "#elementor-action:action=off_canvas:open&settings=eyJ9"), aaBase);
});
test("stripActionAnchor: keeps a real SPA hash route", () => {
    const url = aaBase + "#/products?page=2";
    assert.equal(stripActionAnchor(url), url);
});
test("stripActionAnchor: keeps a bare named anchor", () => {
    const url = aaBase + "#section-2";
    assert.equal(stripActionAnchor(url), url);
});
test("stripActionAnchor: keeps token:colon fragment with no '=' payload", () => {
    const url = aaBase + "#tab:overview";
    assert.equal(stripActionAnchor(url), url);
});
test("stripActionAnchor: returns a url with no fragment unchanged", () => {
    assert.equal(stripActionAnchor(aaBase), aaBase);
});
test("stripActionAnchor: does not throw on malformed percent-encoding", () => {
    const url = aaBase + "#elementor-action:action=x&bad=%E0%A4%A";
    assert.doesNotThrow(() => stripActionAnchor(url));
});
test("actionAnchorStripEnabled: reads env at call time, default false, true only for 'true'", () => {
    delete process.env.STRIP_ACTION_ANCHORS;
    assert.equal(actionAnchorStripEnabled(), false);
    process.env.STRIP_ACTION_ANCHORS = "TRUE";
    assert.equal(actionAnchorStripEnabled(), true);
    process.env.STRIP_ACTION_ANCHORS = "1";
    assert.equal(actionAnchorStripEnabled(), false);
    delete process.env.STRIP_ACTION_ANCHORS;
});
