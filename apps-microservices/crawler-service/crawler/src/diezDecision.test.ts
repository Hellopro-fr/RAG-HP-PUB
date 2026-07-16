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
    assert.equal(classifyFragment("foo.bar.baz.qux.lorem.ipsum.dolor"), "ambiguous"); // 33 chars, dots → not a valid HTML id
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

test("classifyFragment: rule 5 — id with digits is anchor (digit fix)", () => {
    assert.equal(classifyFragment("section2"), "anchor");
    assert.equal(classifyFragment("product12345section67890abcdef"), "anchor"); // 30 chars
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
    const url = "https://example.com/page#foo.bar.baz.qux.lorem.ipsum.dolor";
    recordClassification(url);
    assert.equal(context.diezClassification.ambiguous, 1);
    assert.deepEqual(context.diezClassification.samplesForTier2, [url]);
});

test("recordClassification: samplesForTier2 capped at 50", () => {
    resetContextState();
    for (let i = 0; i < 60; i++) {
        recordClassification(`https://example.com/p#foo.bar.baz.qux${i}`);
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
        recordClassification(`https://e.com/p#foo.bar.baz.qux${i}`);
    }
    for (let i = 0; i < 5; i++) recordClassification(`https://e.com/p#top${i}`);
    for (let i = 0; i < 5; i++) recordClassification(`https://e.com/p#/r${i}`);
    assert.equal(maybeCommitDecision(), "promoteTier2");
});

test("maybeCommitDecision: 100 samples mixed below confidence returns escalate", () => {
    resetContextState();
    for (let i = 0; i < 40; i++) recordClassification(`https://e.com/p#top${i}`);
    for (let i = 0; i < 40; i++) recordClassification(`https://e.com/p#/r${i}`);
    for (let i = 0; i < 20; i++) recordClassification(`https://e.com/p#foo.bar.baz.qux${i}`); // ambiguous (dots): 20% < 40% → no promoteTier2
    assert.equal(maybeCommitDecision(), "escalate");
});

import fs from "node:fs";
import path from "node:path";
import os from "node:os";
import { commitSkipDiez, commitBypassDiez, getDiezDecisionMode } from "./diezDecision.js";

const makeTmpStorage = (): string => {
    return fs.mkdtempSync(path.join(os.tmpdir(), "diez-test-"));
};

test("commitSkipDiez: flips flag, sets committed, writes persistence file", () => {
    resetContextState();
    const storage = makeTmpStorage();
    context.config.skipDiez = false;
    for (let i = 0; i < 7; i++) recordClassification(`https://e.com/p#top${i}`);

    commitSkipDiez(storage);

    assert.equal(context.config.skipDiez, true);
    assert.equal(context.diezDecisionCommitted, true);

    const filePath = path.join(storage, "_diez_decision.json");
    assert.ok(fs.existsSync(filePath), "persistence file not written");
    const payload = JSON.parse(fs.readFileSync(filePath, "utf-8"));
    assert.equal(payload.decision, "skipDiez");
    assert.equal(payload.tier, 1);
    assert.ok(typeof payload.committedAt === "string");
    assert.equal(payload.counts.total, 7);
    assert.equal(payload.counts.anchor, 7);

    fs.rmSync(storage, { recursive: true, force: true });
});

test("commitBypassDiez: flips flag, sets committed, writes persistence file", () => {
    resetContextState();
    const storage = makeTmpStorage();
    context.config.bypassDiez = false;
    for (let i = 0; i < 5; i++) recordClassification(`https://e.com/p#/r${i}`);

    commitBypassDiez(storage);

    assert.equal(context.config.bypassDiez, true);
    assert.equal(context.diezDecisionCommitted, true);

    const payload = JSON.parse(fs.readFileSync(path.join(storage, "_diez_decision.json"), "utf-8"));
    assert.equal(payload.decision, "bypassDiez");

    fs.rmSync(storage, { recursive: true, force: true });
});

test("commit flag stops further recording", () => {
    resetContextState();
    const storage = makeTmpStorage();
    for (let i = 0; i < 5; i++) recordClassification(`https://e.com/p#top${i}`);
    commitSkipDiez(storage);

    recordClassification("https://e.com/p#another");
    assert.equal(context.diezClassification.total, 5, "counters should not change after commit");

    fs.rmSync(storage, { recursive: true, force: true });
});

test("persistence file does not include samplesForTier2", () => {
    resetContextState();
    const storage = makeTmpStorage();
    // Add some ambiguous samples (dots → ambiguous, so samplesForTier2 is populated)
    for (let i = 0; i < 3; i++) recordClassification(`https://e.com/p#foo.bar.baz.qux${i}`);
    for (let i = 0; i < 4; i++) recordClassification(`https://e.com/p#top${i}`);
    commitSkipDiez(storage);

    const payload = JSON.parse(fs.readFileSync(path.join(storage, "_diez_decision.json"), "utf-8"));
    assert.ok(!("samplesForTier2" in payload.counts), "samplesForTier2 should be dropped from counts");

    fs.rmSync(storage, { recursive: true, force: true });
});

import { readPersistedDecision } from "./diezDecision.js";

test("readPersistedDecision: no file returns false, no state change", () => {
    resetContextState();
    const storage = makeTmpStorage();
    context.config.skipDiez = false;
    context.config.bypassDiez = false;

    const loaded = readPersistedDecision(storage);

    assert.equal(loaded, false);
    assert.equal(context.config.skipDiez, false);
    assert.equal(context.diezDecisionCommitted, false);

    fs.rmSync(storage, { recursive: true, force: true });
});

test("readPersistedDecision: valid skipDiez file applies to context", () => {
    resetContextState();
    const storage = makeTmpStorage();
    fs.writeFileSync(
        path.join(storage, "_diez_decision.json"),
        JSON.stringify({ decision: "skipDiez", tier: 1, committedAt: "2026-04-17T00:00:00Z", counts: { anchor: 7, spa: 0, ambiguous: 0, total: 7 } })
    );
    context.config.skipDiez = false;

    const loaded = readPersistedDecision(storage);

    assert.equal(loaded, true);
    assert.equal(context.config.skipDiez, true);
    assert.equal(context.diezDecisionCommitted, true);

    fs.rmSync(storage, { recursive: true, force: true });
});

test("readPersistedDecision: valid bypassDiez file applies to context", () => {
    resetContextState();
    const storage = makeTmpStorage();
    fs.writeFileSync(
        path.join(storage, "_diez_decision.json"),
        JSON.stringify({ decision: "bypassDiez", tier: 1, committedAt: "2026-04-17T00:00:00Z", counts: { anchor: 0, spa: 5, ambiguous: 0, total: 5 } })
    );
    context.config.bypassDiez = false;

    const loaded = readPersistedDecision(storage);

    assert.equal(loaded, true);
    assert.equal(context.config.bypassDiez, true);
    assert.equal(context.diezDecisionCommitted, true);

    fs.rmSync(storage, { recursive: true, force: true });
});

test("readPersistedDecision: malformed file returns false, no crash", () => {
    resetContextState();
    const storage = makeTmpStorage();
    fs.writeFileSync(path.join(storage, "_diez_decision.json"), "not-json");

    const loaded = readPersistedDecision(storage);

    assert.equal(loaded, false);
    assert.equal(context.diezDecisionCommitted, false);

    fs.rmSync(storage, { recursive: true, force: true });
});

test("commitSkipDiez tier-2 meta writes source + evidence to the decision file", () => {
    resetContextState();
    const storage = makeTmpStorage();
    const evidence = { compared: 3, matches: 3, mismatches: 0, unusable: 0 };
    commitSkipDiez(storage, { tier: 2, source: "tier2", evidence });
    const payload = JSON.parse(fs.readFileSync(path.join(storage, "_diez_decision.json"), "utf-8"));
    assert.equal(payload.source, "tier2");
    assert.equal(payload.tier, 2);
    assert.deepEqual(payload.evidence, evidence);
    fs.rmSync(storage, { recursive: true, force: true });
});

test("getDiezDecisionMode reports defaulted-bypassdiez for a default-source commit", () => {
    resetContextState();
    const storage = makeTmpStorage();
    commitBypassDiez(storage, { tier: 2, source: "default" });
    assert.equal(getDiezDecisionMode(undefined), "defaulted-bypassdiez");
    fs.rmSync(storage, { recursive: true, force: true });
});

test("readPersistedDecision restores tier-2 source → getDiezDecisionMode reports tier2-skipdiez (OOM relaunch)", () => {
    // Force _committedSource to a non-tier2 value first (a fresh process defaults to "tier1").
    resetContextState();
    context.config.skipDiez = false;
    context.config.bypassDiez = false;
    const seed = makeTmpStorage();
    commitBypassDiez(seed, { source: "tier1" }); // sets _committedSource = "tier1"
    fs.rmSync(seed, { recursive: true, force: true });

    // Simulate relaunch: a prior run persisted a tier-2 skipDiez decision.
    resetContextState();
    context.config.skipDiez = false;
    context.config.bypassDiez = false;
    const storage = makeTmpStorage();
    fs.writeFileSync(
        path.join(storage, "_diez_decision.json"),
        JSON.stringify({ decision: "skipDiez", tier: 2, source: "tier2", evidence: { compared: 3, matches: 3, mismatches: 0, unusable: 0 } })
    );

    assert.equal(readPersistedDecision(storage), true);
    assert.equal(context.config.skipDiez, true);
    assert.equal(getDiezDecisionMode(undefined), "tier2-skipdiez");

    fs.rmSync(storage, { recursive: true, force: true });
});

test("readPersistedDecision: legacy file without source reports tier1 (backward compat)", () => {
    resetContextState();
    context.config.skipDiez = false;
    context.config.bypassDiez = false;
    const storage = makeTmpStorage();
    fs.writeFileSync(
        path.join(storage, "_diez_decision.json"),
        JSON.stringify({ decision: "bypassDiez", tier: 1, committedAt: "2026-04-17T00:00:00Z", counts: { anchor: 0, spa: 5, ambiguous: 0, total: 5 } })
    );
    assert.equal(readPersistedDecision(storage), true);
    assert.equal(getDiezDecisionMode(undefined), "tier1-bypassdiez");
    fs.rmSync(storage, { recursive: true, force: true });
});
