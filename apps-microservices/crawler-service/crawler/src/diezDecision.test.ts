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
