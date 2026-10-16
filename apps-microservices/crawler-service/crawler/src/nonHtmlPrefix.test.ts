// apps-microservices/crawler-service/crawler/src/nonHtmlPrefix.test.ts
import { test } from "node:test";
import assert from "node:assert/strict";
import {
    NONHTML_PREFIX_DEFAULTS,
    createNonHtmlPrefixState,
    decide,
    isKeyBlocking,
    normalizeUrlIdentity,
    prefixKey,
    recordHtml,
    recordNonHtml,
    recordProbeFailure,
    resolveNonHtmlPrefixMode,
    resolveNonHtmlPrefixParams,
    resolvePositiveInt,
    type NonHtmlPrefixParams,
    type NonHtmlPrefixState,
    type PrefixEntry,
    type Probation,
} from "./nonHtmlPrefix.js";

const P: NonHtmlPrefixParams = { minNonHtml: 3, probes: 2, isolatedMax: 2 };
const NOW = "2026-10-16T10:00:00.000Z";
const LATER = "2026-10-16T11:00:00.000Z";
const KEY = "h.fr/image";

/** A no-extension URL under the key `h.fr/image`. */
const img = (i: number): string => `https://h.fr/image/p${i}`;
/** A key-less URL (parent directory is the root). */
const bare = (i: number): string => `https://h.fr/telechargement?id=${i}`;

const fresh = (): NonHtmlPrefixState => createNonHtmlPrefixState({ ...P });
const entry = (over: Partial<PrefixEntry> = {}): PrefixEntry => ({
    nonHtml: 0,
    sawHtml: false,
    confirmed: false,
    confirmedAt: null,
    probation: null,
    ...over,
});
const probation = (over: Partial<Probation> = {}): Probation => ({
    admitted: 0,
    probeUrl: null,
    resolved: false,
    ...over,
});
const withEntry = (e: PrefixEntry): NonHtmlPrefixState => {
    const s = fresh();
    s.prefixes.set(KEY, e);
    return s;
};
const probing = (p: Partial<Probation>): NonHtmlPrefixState =>
    withEntry(entry({ nonHtml: 5, probation: probation(p) }));
const got = (s: NonHtmlPrefixState, key: string = KEY): PrefixEntry => {
    const e = s.prefixes.get(key);
    assert.ok(e, `no entry for ${key}`);
    return e;
};
const never = (): boolean => false;

// ---------------------------------------------------------------- modes and numbers

test("resolveNonHtmlPrefixMode: shadow and on pass through, trimmed and case-folded", () => {
    assert.equal(resolveNonHtmlPrefixMode("shadow"), "shadow");
    assert.equal(resolveNonHtmlPrefixMode("on"), "on");
    assert.equal(resolveNonHtmlPrefixMode("  ON "), "on");
    assert.equal(resolveNonHtmlPrefixMode("Shadow"), "shadow");
});

test("resolveNonHtmlPrefixMode: undefined, empty, off and unknown values are off", () => {
    for (const raw of [undefined, "", "   ", "off", "true", "1", "enabled", "shadow2"]) {
        assert.equal(resolveNonHtmlPrefixMode(raw), "off", `raw=${JSON.stringify(raw)}`);
    }
});

test("resolvePositiveInt: a positive integer string is parsed (trimmed)", () => {
    assert.equal(resolvePositiveInt("5", 9), 5);
    assert.equal(resolvePositiveInt(" 12 ", 9), 12);
    assert.equal(resolvePositiveInt("007", 9), 7);
});

test("resolvePositiveInt: undefined, empty, non-integer and non-positive fall back (empty is never 0)", () => {
    for (const raw of [undefined, "", "abc", "0", "-1", "2.5", "   ", "1e3", "00"]) {
        assert.equal(resolvePositiveInt(raw, 9), 9, `raw=${JSON.stringify(raw)}`);
    }
});

test("resolveNonHtmlPrefixParams: no variable gives the defaults, as a fresh object", () => {
    assert.deepEqual(NONHTML_PREFIX_DEFAULTS, { minNonHtml: 5, probes: 3, isolatedMax: 10000 });
    const r = resolveNonHtmlPrefixParams({});
    assert.deepEqual(r, NONHTML_PREFIX_DEFAULTS);
    assert.notEqual(r, NONHTML_PREFIX_DEFAULTS, "never the shared defaults object");
});

test("resolveNonHtmlPrefixParams: each variable feeds its own field", () => {
    const r = resolveNonHtmlPrefixParams({
        NONHTML_PREFIX_MIN: "8",
        NONHTML_PREFIX_PROBES: "2",
        NONHTML_ISOLATED_MAX: "50",
    });
    assert.deepEqual(r, { minNonHtml: 8, probes: 2, isolatedMax: 50 });
    assert.deepEqual(resolveNonHtmlPrefixParams({ NONHTML_PREFIX_MIN: "8" }), {
        minNonHtml: 8,
        probes: 3,
        isolatedMax: 10000,
    });
});

test("resolveNonHtmlPrefixParams: empty or invalid values keep the defaults, never 0", () => {
    for (const bad of ["", "0", "abc", "-4", "2.5"]) {
        const r = resolveNonHtmlPrefixParams({
            NONHTML_PREFIX_MIN: bad,
            NONHTML_PREFIX_PROBES: bad,
            NONHTML_ISOLATED_MAX: bad,
        });
        assert.deepEqual(r, NONHTML_PREFIX_DEFAULTS, `bad=${JSON.stringify(bad)}`);
    }
});

// ---------------------------------------------------------------- identity and key

test("normalizeUrlIdentity: strips trailing slashes only", () => {
    assert.equal(normalizeUrlIdentity("https://h.fr/a/"), "https://h.fr/a");
    assert.equal(normalizeUrlIdentity("https://h.fr/a///"), "https://h.fr/a");
    assert.equal(normalizeUrlIdentity("https://h.fr/a"), "https://h.fr/a");
    assert.equal(normalizeUrlIdentity("https://h.fr/"), "https://h.fr");
    assert.equal(normalizeUrlIdentity("https://h.fr/a?x=1"), "https://h.fr/a?x=1");
});

test("prefixKey: host + parent directory, query and fragment ignored (index examples)", () => {
    assert.equal(prefixKey("https://www.marsaleix.fr/image/_1AAAB-x?y=1#z"), "www.marsaleix.fr/image");
    assert.equal(prefixKey("https://h.fr/telechargement?id=12"), null);
});

test("prefixKey: root, directory-only, empty and invalid URLs are key-less", () => {
    assert.equal(prefixKey("https://h.fr/"), null);
    assert.equal(prefixKey("https://h.fr"), null);
    assert.equal(prefixKey("https://h.fr/image/"), null, "posix dirname of /image/ is /");
    assert.equal(prefixKey("not a url"), null);
    assert.equal(prefixKey(""), null);
});

test("prefixKey: port and depth kept, scheme and host case ignored", () => {
    assert.equal(prefixKey("https://h.fr:8443/a/b"), "h.fr:8443/a");
    assert.equal(prefixKey("https://h.fr/a/b/c"), "h.fr/a/b");
    assert.equal(prefixKey("http://h.fr/image/x"), prefixKey("https://h.fr/image/x"));
    assert.equal(prefixKey("https://H.FR/image/x"), "h.fr/image");
    assert.notEqual(prefixKey("https://www.h.fr/image/x"), prefixKey("https://h.fr/image/x"));
});

// ---------------------------------------------------------------- state

test("createNonHtmlPrefixState: empty collections, params kept", () => {
    const s = createNonHtmlPrefixState({ ...P });
    assert.deepEqual(s.params, P);
    assert.equal(s.prefixes.size, 0);
    assert.equal(s.isolated.size, 0);
    assert.equal(s.loadedIsolated.size, 0);
});

test("isKeyBlocking: confirmed or K reached, and never once HTML was seen", () => {
    assert.equal(isKeyBlocking(entry({ confirmed: true }), P), true);
    assert.equal(isKeyBlocking(entry({ nonHtml: 3 }), P), true);
    assert.equal(isKeyBlocking(entry({ nonHtml: 2 }), P), false);
    assert.equal(isKeyBlocking(entry({ nonHtml: 9, confirmed: true, sawHtml: true }), P), false);
});

// ---------------------------------------------------------------- recordNonHtml

test("recordNonHtml 1: an ignored-extension URL changes nothing", () => {
    const s = fresh();
    assert.equal(recordNonHtml(s, "https://h.fr/image/p1.jpg", NOW), "ignored");
    assert.equal(recordNonHtml(s, "https://h.fr/telechargement.pdf", NOW), "ignored");
    assert.equal(s.prefixes.size, 0);
    assert.equal(s.isolated.size, 0);
});

test("recordNonHtml 2: a key-less URL is isolated once, deduplicated on identity, capped at isolatedMax", () => {
    const s = fresh();
    assert.equal(recordNonHtml(s, bare(1), NOW), "isolated");
    assert.equal(recordNonHtml(s, bare(1), NOW), "ignored", "duplicate");
    assert.equal(recordNonHtml(s, "https://h.fr/doc", NOW), "isolated");
    assert.equal(recordNonHtml(s, "https://h.fr/doc/", NOW), "ignored", "trailing slash is the same identity");
    assert.equal(recordNonHtml(s, bare(3), NOW), "ignored", "cap of 2 reached");
    assert.deepEqual([...s.isolated], [bare(1), "https://h.fr/doc"]);
    assert.equal(s.prefixes.size, 0);
});

test("recordNonHtml 3: under a key that served HTML the count grows but nothing is learned", () => {
    const s = fresh();
    assert.equal(recordHtml(s, img(0)), "none");
    for (const i of [1, 2, 3, 4]) assert.equal(recordNonHtml(s, img(i), NOW), "counted");
    const e = got(s);
    assert.equal(e.nonHtml, 4);
    assert.equal(e.sawHtml, true);
    assert.equal(e.confirmedAt, null);
    assert.equal(isKeyBlocking(e, s.params), false);
    assert.equal(s.isolated.size, 0);
});

test("recordNonHtml 3/8/7: first hits create the entry and are isolated; the K-th hit learns", () => {
    const s = fresh();
    assert.equal(recordNonHtml(s, img(1), NOW), "isolated");
    assert.deepEqual(got(s), entry({ nonHtml: 1 }));
    assert.equal(recordNonHtml(s, img(2), NOW), "isolated");
    assert.equal(s.isolated.size, 2);
    assert.equal(recordNonHtml(s, img(3), NOW), "learned");
    const e = got(s);
    assert.equal(e.nonHtml, 3);
    assert.equal(e.confirmedAt, NOW);
    assert.equal(e.confirmed, false);
    assert.equal(isKeyBlocking(e, s.params), true);
    assert.equal(s.isolated.size, 2, "the learning hit is not isolated");
});

test("recordNonHtml 8: under K, a hit at the isolated cap or a repeated identity is only counted", () => {
    const s = fresh();
    recordNonHtml(s, bare(1), NOW);
    recordNonHtml(s, bare(2), NOW);
    assert.equal(s.isolated.size, 2);
    assert.equal(recordNonHtml(s, img(1), NOW), "counted", "cap reached");
    assert.equal(s.isolated.size, 2);
    assert.equal(got(s).nonHtml, 1);

    const t = fresh();
    assert.equal(recordNonHtml(t, img(1), NOW), "isolated");
    assert.equal(recordNonHtml(t, `${img(1)}/`, NOW), "counted", "same identity after trailing slash");
    assert.equal(got(t).nonHtml, 2);
    assert.equal(t.isolated.size, 1);
});

test("recordNonHtml 4/6: once blocking, further hits are counted and confirmedAt is kept", () => {
    const s = fresh();
    for (const i of [1, 2, 3]) recordNonHtml(s, img(i), NOW);
    assert.equal(recordNonHtml(s, img(4), LATER), "counted");
    const e = got(s);
    assert.equal(e.nonHtml, 4);
    assert.equal(e.confirmedAt, NOW);
});

test("recordNonHtml 5: any non-HTML under an unresolved probation confirms the key", () => {
    const s = withEntry(entry({ nonHtml: 1, probation: probation({ admitted: 1, probeUrl: img(9) }) }));
    assert.equal(recordNonHtml(s, img(5), NOW), "confirmed", "a URL other than the probe also confirms");
    const e = got(s);
    assert.equal(e.nonHtml, 2);
    assert.equal(e.confirmed, true);
    assert.equal(e.confirmedAt, NOW);
    assert.deepEqual(e.probation, { admitted: 1, probeUrl: null, resolved: true });
});

test("recordNonHtml 5 before 6: a previous-crawl key already at K is still confirmed by the probe", () => {
    const s = withEntry(entry({ nonHtml: 7, confirmedAt: "2026-10-01T00:00:00.000Z", probation: probation() }));
    assert.equal(recordNonHtml(s, img(1), NOW), "confirmed");
    assert.equal(got(s).confirmedAt, NOW);
    assert.equal(got(s).nonHtml, 8);
});

test("recordNonHtml 6: a resolved probation no longer re-confirms", () => {
    const s = withEntry(
        entry({
            nonHtml: 4,
            confirmed: true,
            confirmedAt: NOW,
            probation: probation({ admitted: 3, resolved: true }),
        }),
    );
    assert.equal(recordNonHtml(s, img(1), LATER), "counted");
    assert.equal(got(s).confirmedAt, NOW);
    assert.equal(got(s).nonHtml, 5);
});

test("recordNonHtml: keys are counted independently (host + parent directory)", () => {
    const s = fresh();
    const urls = [
        "https://h.fr/image/a",
        "https://h.fr/image/b",
        "https://h.fr/pdf/a",
        "https://h.fr/pdf/b",
        "https://other.fr/image/a",
        "https://other.fr/image/b",
    ];
    for (const u of urls) assert.notEqual(recordNonHtml(s, u, NOW), "learned");
    assert.deepEqual([...s.prefixes.keys()], ["h.fr/image", "h.fr/pdf", "other.fr/image"]);
    for (const e of s.prefixes.values()) assert.equal(e.nonHtml, 2);
});

// ---------------------------------------------------------------- recordHtml

test("recordHtml: a key-less URL is none and creates nothing", () => {
    const s = fresh();
    assert.equal(recordHtml(s, bare(1)), "none");
    assert.equal(s.prefixes.size, 0);
});

test("recordHtml: an absent key is created with the veto set", () => {
    const s = fresh();
    assert.equal(recordHtml(s, img(1)), "none");
    assert.deepEqual(got(s), entry({ sawHtml: true }));
    assert.equal(recordNonHtml(s, img(2), NOW), "counted", "the veto holds");
});

test("recordHtml: a learned (blocking) key is released", () => {
    const s = fresh();
    for (const i of [1, 2, 3]) recordNonHtml(s, img(i), NOW);
    assert.equal(recordHtml(s, img(7)), "released");
    const e = got(s);
    assert.equal(e.sawHtml, true);
    assert.equal(e.nonHtml, 3);
    assert.equal(isKeyBlocking(e, s.params), false);
    assert.equal(decide(s, img(8), never), "allow");
});

test("recordHtml: a confirmed key under K is released", () => {
    const s = withEntry(entry({ nonHtml: 1, confirmed: true }));
    assert.equal(recordHtml(s, img(1)), "released");
    assert.equal(got(s).sawHtml, true);
});

test("recordHtml: a key under an unresolved probation is released and the probation closed", () => {
    const s = withEntry(entry({ nonHtml: 1, probation: probation({ admitted: 1, probeUrl: img(1) }) }));
    assert.equal(recordHtml(s, img(1)), "released");
    assert.equal(got(s).sawHtml, true);
    assert.deepEqual(got(s).probation, { admitted: 1, probeUrl: null, resolved: true });
});

test("recordHtml: a key under K with no probation only gets the veto", () => {
    const s = withEntry(entry({ nonHtml: 1 }));
    assert.equal(recordHtml(s, img(1)), "none");
    assert.equal(got(s).sawHtml, true);
});

test("recordHtml: a second HTML hit on a vetoed key is none", () => {
    const s = fresh();
    recordHtml(s, img(1));
    assert.equal(recordHtml(s, img(2)), "none");
    assert.equal(got(s).sawHtml, true);
});

// ---------------------------------------------------------------- recordProbeFailure

test("recordProbeFailure: a key-less URL is false", () => {
    const s = probing({ admitted: 1, probeUrl: bare(1) });
    assert.equal(recordProbeFailure(s, bare(1)), false);
});

test("recordProbeFailure: an unknown key is false", () => {
    assert.equal(recordProbeFailure(fresh(), img(1)), false);
});

test("recordProbeFailure: an entry without probation is false and unchanged", () => {
    const s = withEntry(entry({ nonHtml: 5 }));
    assert.equal(recordProbeFailure(s, img(1)), false);
    assert.deepEqual(got(s), entry({ nonHtml: 5 }));
});

test("recordProbeFailure: a resolved probation is false and unchanged", () => {
    const s = probing({ admitted: 3, resolved: true });
    assert.equal(recordProbeFailure(s, img(1)), false);
    assert.deepEqual(got(s).probation, { admitted: 3, probeUrl: null, resolved: true });
    assert.equal(got(s).confirmed, false);
});

test("recordProbeFailure: a URL other than the in-flight probe is false and unchanged", () => {
    const s = probing({ admitted: 1, probeUrl: img(1) });
    assert.equal(recordProbeFailure(s, img(2)), false);
    assert.deepEqual(got(s).probation, { admitted: 1, probeUrl: img(1), resolved: false });
});

test("recordProbeFailure: the probe failing with admissions left frees the slot, key still in probation", () => {
    const s = probing({ admitted: 1, probeUrl: img(1) });
    assert.equal(recordProbeFailure(s, img(1)), true);
    assert.deepEqual(got(s).probation, { admitted: 1, probeUrl: null, resolved: false });
    assert.equal(got(s).confirmed, false);
});

test("recordProbeFailure: the last admitted probe failing resolves the probation as confirmed", () => {
    const s = probing({ admitted: 2, probeUrl: img(1) });
    assert.equal(recordProbeFailure(s, img(1)), true);
    assert.deepEqual(got(s).probation, { admitted: 2, probeUrl: null, resolved: true });
    assert.equal(got(s).confirmed, true);
    assert.equal(isKeyBlocking(got(s), s.params), true);
});

test("recordProbeFailure: the failed URL is matched on normalized identity", () => {
    const s = probing({ admitted: 1, probeUrl: img(1) });
    assert.equal(recordProbeFailure(s, `${img(1)}/`), true);
    assert.equal(got(s).probation?.probeUrl, null);
});

// ---------------------------------------------------------------- decide

test("decide 1: an exempt URL is allowed even if blocked elsewhere; the predicate sees the normalized identity", () => {
    const s = withEntry(entry({ nonHtml: 9, confirmed: true }));
    s.loadedIsolated.add(img(1));
    const seen: string[] = [];
    const r = decide(s, `${img(1)}/`, (n) => {
        seen.push(n);
        return true;
    });
    assert.equal(r, "allow");
    assert.deepEqual(seen, [img(1)]);
});

test("decide 2: a loadedIsolated URL is blocked before its key is looked at", () => {
    const s = withEntry(entry({ sawHtml: true, nonHtml: 1 }));
    s.loadedIsolated.add(img(1));
    s.loadedIsolated.add(bare(1));
    assert.equal(decide(s, img(1), never), "block");
    assert.equal(decide(s, `${img(1)}/`, never), "block");
    assert.equal(decide(s, bare(1), never), "block");
    assert.equal(decide(s, img(2), never), "allow", "same key, vetoed, not isolated");
});

test("decide 3: key-less, unknown key and HTML-vetoed key are allowed", () => {
    const s = withEntry(entry({ sawHtml: true, confirmed: true, nonHtml: 9 }));
    assert.equal(decide(s, bare(1), never), "allow");
    assert.equal(decide(s, "https://h.fr/other/x", never), "allow");
    assert.equal(decide(s, img(1), never), "allow");
});

test("decide 4a: the in-flight probe URL is probed again (retry of the same probe)", () => {
    const s = withEntry(entry({ nonHtml: 6, probation: probation({ admitted: 1, probeUrl: img(1) }) }));
    assert.equal(decide(s, `${img(1)}/`, never), "probe");
    assert.deepEqual(got(s).probation, { admitted: 1, probeUrl: img(1), resolved: false });
});

test("decide 4b: another URL while a probe is in flight is blocked, nothing changes", () => {
    const s = withEntry(entry({ nonHtml: 6, probation: probation({ admitted: 1, probeUrl: img(1) }) }));
    assert.equal(decide(s, img(2), never), "block");
    assert.deepEqual(got(s).probation, { admitted: 1, probeUrl: img(1), resolved: false });
});

test("decide 4c: with no probe in flight and admissions left, the URL becomes the probe", () => {
    const s = withEntry(entry({ nonHtml: 6, probation: probation({ admitted: 1 }) }));
    assert.equal(decide(s, img(2), never), "probe");
    assert.deepEqual(got(s).probation, { admitted: 2, probeUrl: img(2), resolved: false });
    assert.equal(decide(s, img(3), never), "block", "a probe is now in flight");
});

test("decide 4d: with admissions exhausted and no probe, the probation resolves as confirmed and blocks", () => {
    const s = withEntry(entry({ nonHtml: 6, probation: probation({ admitted: 2 }) }));
    assert.equal(decide(s, img(3), never), "block");
    assert.deepEqual(got(s).probation, { admitted: 2, probeUrl: null, resolved: true });
    assert.equal(got(s).confirmed, true);
    assert.equal(decide(s, img(4), never), "block");
});

test("decide 4: two probes timing out in turn leave the key blocking (spec 3.3, exhausted without signal)", () => {
    const s = withEntry(entry({ nonHtml: 6, probation: probation() }));
    assert.equal(decide(s, img(1), never), "probe");
    assert.equal(recordProbeFailure(s, img(1)), true);
    assert.equal(decide(s, img(2), never), "probe");
    assert.equal(recordProbeFailure(s, img(2)), true);
    assert.deepEqual(got(s).probation, { admitted: 2, probeUrl: null, resolved: true });
    assert.equal(got(s).confirmed, true);
    assert.equal(decide(s, img(3), never), "block");
});

test("decide 5: without probation, a key blocks from K and allows below K", () => {
    const s = withEntry(entry({ nonHtml: 2 }));
    assert.equal(decide(s, img(1), never), "allow");
    got(s).nonHtml = 3;
    assert.equal(decide(s, img(1), never), "block");
});

test("decide 5: a confirmed key under K blocks", () => {
    const s = withEntry(entry({ nonHtml: 1, confirmed: true }));
    assert.equal(decide(s, img(1), never), "block");
});

test("lifecycle: learn at K, block, then a later HTML page releases the key for the whole crawl", () => {
    const s = fresh();
    for (const i of [1, 2, 3]) recordNonHtml(s, img(i), NOW);
    assert.equal(decide(s, img(4), never), "block");
    assert.equal(decide(s, "https://h.fr/", never), "allow", "key-less URL");
    assert.equal(recordHtml(s, img(4)), "released");
    assert.equal(decide(s, img(5), never), "allow");
    assert.equal(recordNonHtml(s, img(6), LATER), "counted");
    assert.equal(decide(s, img(7), never), "allow", "the veto holds");
});
