import { test } from "node:test";
import assert from "node:assert/strict";
import { classifyFragment } from "./diezDecision.js";

test("classifyFragment: rule 1 — empty fragment is anchor", () => {
    assert.equal(classifyFragment(""), "anchor");
});

test("classifyFragment: rule 2 — starts with / is spa", () => {
    assert.equal(classifyFragment("/products/1"), "spa");
    assert.equal(classifyFragment("/"), "spa");
    assert.equal(classifyFragment("/foo"), "spa");
});

test("classifyFragment: rule 2 — hashbang !/ is spa (strip leading !)", () => {
    assert.equal(classifyFragment("!/route"), "spa");
    assert.equal(classifyFragment("!/products/123"), "spa");
});

test("classifyFragment: rule 2 — URL-encoded slash is spa", () => {
    assert.equal(classifyFragment("%2Ffoo"), "spa");
});

test("classifyFragment: rule 3 — contains / anywhere is spa", () => {
    assert.equal(classifyFragment("foo/bar"), "spa");
});

test("classifyFragment: rule 4 — & and = is spa", () => {
    assert.equal(classifyFragment("a=1&b=2"), "spa");
    assert.equal(classifyFragment("state=xyz&user=abc"), "spa");
});

test("classifyFragment: rule 4 — starts with ? is spa", () => {
    assert.equal(classifyFragment("?id=5"), "spa");
});

test("classifyFragment: rule 5 — HTML id convention (section-3) is anchor", () => {
    assert.equal(classifyFragment("section-3"), "anchor");
    assert.equal(classifyFragment("faq_item"), "anchor");
    assert.equal(classifyFragment("h-title"), "anchor");
});

test("classifyFragment: rule 6 — short alphanumeric is anchor", () => {
    assert.equal(classifyFragment("top"), "anchor");
    assert.equal(classifyFragment("abc123"), "anchor");
    assert.equal(classifyFragment("a"), "anchor");
});

test("classifyFragment: rule 7 — long random string is ambiguous", () => {
    assert.equal(classifyFragment("xkc9f8h2kj34lmn7pqr5stuvwxyz"), "ambiguous");
});

test("classifyFragment: rule 7 — non-ASCII is ambiguous", () => {
    assert.equal(classifyFragment("état"), "ambiguous");
});

test("classifyFragment: rule 7 — mixed specials without / or & is ambiguous", () => {
    assert.equal(classifyFragment("foo.bar.baz"), "ambiguous");
});

test("classifyFragment: length boundary — 50-char anchor-id-pattern is still anchor", () => {
    const frag = "a" + "b".repeat(49); // 50 chars total, matches rule 5 length ≤ 50
    assert.equal(classifyFragment(frag), "anchor");
});

test("classifyFragment: length boundary — 51-char id-pattern falls to rule 7", () => {
    const frag = "a" + "b".repeat(50); // 51 chars, rule 5 requires ≤ 50, rule 6 requires ≤ 20 → falls to 7
    assert.equal(classifyFragment(frag), "ambiguous");
});

test("classifyFragment: length boundary — 20-char short-alphanum is anchor", () => {
    const frag = "abc123def456ghi789jk"; // 20 chars, matches rule 6
    assert.equal(classifyFragment(frag), "anchor");
});

test("classifyFragment: rule precedence — fragment with / and short length is spa (rule 3 beats anything)", () => {
    assert.equal(classifyFragment("a/b"), "spa");
});

import { context } from "./context.js";
import { recordClassification, maybeCommitDecision } from "./diezDecision.js";

const resetContextState = () => {
    context.diezClassification = { anchor: 0, spa: 0, ambiguous: 0, total: 0, samplesForTier2: [] };
    context.diezDecisionCommitted = false;
};

test("recordClassification: increments correct counter", () => {
    resetContextState();
    recordClassification("https://example.com/page#top");
    assert.equal(context.diezClassification.anchor, 1);
    assert.equal(context.diezClassification.total, 1);
});

test("recordClassification: ambiguous URL is appended to samplesForTier2", () => {
    resetContextState();
    const url = "https://example.com/page#xkc9f8h2kj34lmn7pqr5stuvwxyz";
    recordClassification(url);
    assert.equal(context.diezClassification.ambiguous, 1);
    assert.deepEqual(context.diezClassification.samplesForTier2, [url]);
});

test("recordClassification: samplesForTier2 capped at 50", () => {
    resetContextState();
    for (let i = 0; i < 60; i++) {
        recordClassification(`https://example.com/p#xkc9f8h2kj34lmn7pqr5stuvwxyz${i}`);
    }
    assert.equal(context.diezClassification.samplesForTier2.length, 50);
    assert.equal(context.diezClassification.ambiguous, 60);
});

test("recordClassification: URL without # is ignored", () => {
    resetContextState();
    recordClassification("https://example.com/page");
    assert.equal(context.diezClassification.total, 0);
});

test("recordClassification: no-op after decision committed", () => {
    resetContextState();
    context.diezDecisionCommitted = true;
    recordClassification("https://example.com/page#top");
    assert.equal(context.diezClassification.total, 0);
});

test("maybeCommitDecision: below MIN_SAMPLES returns null", () => {
    resetContextState();
    for (let i = 0; i < 4; i++) recordClassification(`https://e.com/p#top${i}`);
    assert.equal(maybeCommitDecision(), null);
});

test("maybeCommitDecision: 5 anchor samples returns skipDiez", () => {
    resetContextState();
    for (const frag of ["top", "bottom", "section-1", "faq", "comments"]) {
        recordClassification(`https://e.com/p#${frag}`);
    }
    assert.equal(maybeCommitDecision(), "skipDiez");
});

test("maybeCommitDecision: 5 spa samples returns bypassDiez", () => {
    resetContextState();
    for (const frag of ["/products/1", "/products/2", "/cart", "/about", "/contact"]) {
        recordClassification(`https://e.com/p#${frag}`);
    }
    assert.equal(maybeCommitDecision(), "bypassDiez");
});

test("maybeCommitDecision: 80/20 split below 90% threshold returns null", () => {
    resetContextState();
    for (const frag of ["top", "bottom", "section-1", "faq"]) {
        recordClassification(`https://e.com/p#${frag}`);
    }
    recordClassification("https://e.com/p#/route");
    assert.equal(maybeCommitDecision(), null);
});

test("maybeCommitDecision: ambiguous ≥ 40% at total ≥ 20 returns promoteTier2", () => {
    resetContextState();
    for (let i = 0; i < 10; i++) {
        recordClassification(`https://e.com/p#xkc9f8h2kj34lmn7pqr5stuvwxyz${i}`);
    }
    for (let i = 0; i < 5; i++) recordClassification(`https://e.com/p#top${i}`);
    for (let i = 0; i < 5; i++) recordClassification(`https://e.com/p#/r${i}`);
    assert.equal(maybeCommitDecision(), "promoteTier2");
});

test("maybeCommitDecision: 100 samples mixed below confidence returns escalate", () => {
    resetContextState();
    for (let i = 0; i < 40; i++) recordClassification(`https://e.com/p#top${i}`);
    for (let i = 0; i < 40; i++) recordClassification(`https://e.com/p#/r${i}`);
    for (let i = 0; i < 20; i++) recordClassification(`https://e.com/p#xkc9f8h2kj34lmn7pqr5stuvwxyz${i}`);
    assert.equal(maybeCommitDecision(), "escalate");
});
