import { test, mock } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import {
    createNonHtmlPrefixState,
    NONHTML_PREFIX_DEFAULTS,
    type NonHtmlPrefixState,
    type PrefixEntry,
} from "./nonHtmlPrefix.js";
import {
    NONHTML_PREFIX_SIDECAR,
    NONHTML_SIDECAR_VERSION,
    currentSidecarPath,
    loadSidecarInto,
    parseNonHtmlPrefixSidecar,
    readSidecarFile,
    resolvePreviousSidecarPath,
    serializeNonHtmlPrefixState,
    writeSidecarFile,
} from "./nonHtmlPrefixSidecar.js";

const TS = "2026-01-01T00:00:00.000Z";

const entry = (over: Partial<PrefixEntry> = {}): PrefixEntry => ({
    nonHtml: 0,
    sawHtml: false,
    confirmed: false,
    confirmedAt: null,
    probation: null,
    ...over,
});

const stateWith = (isolatedMax = 3): NonHtmlPrefixState =>
    createNonHtmlPrefixState({ ...NONHTML_PREFIX_DEFAULTS, minNonHtml: 5, probes: 3, isolatedMax });

const withTmp = (fn: (tmp: string) => void): void => {
    const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "nhps-"));
    try { fn(tmp); } finally { fs.rmSync(tmp, { recursive: true, force: true }); }
};

const EMPTY_BYTES = '{"version":1,"prefixes":{},"urls":[]}';

// ---------------------------------------------------------------- serialize

test("serialize: exact bytes, entries filtered, Map insertion order kept", () => {
    const s = stateWith();
    // blocking by threshold (nonHtml >= K=5), not confirmed
    s.prefixes.set("h/threshold", entry({ nonHtml: 5, confirmedAt: TS }));
    // vetoed by HTML => never persisted, even if confirmed
    s.prefixes.set("h/veto", entry({ nonHtml: 9, sawHtml: true, confirmed: true, confirmedAt: TS }));
    // under K, no probation => not blocking, not persisted
    s.prefixes.set("h/under", entry({ nonHtml: 2 }));
    // confirmed => blocking even under K
    s.prefixes.set("h/confirmed", entry({ nonHtml: 1, confirmed: true, confirmedAt: TS }));
    // unresolved probation => persisted, confirmedAt null kept as null
    s.prefixes.set("h/probing", entry({ nonHtml: 7, probation: { admitted: 1, probeUrl: "https://h/probing/a", resolved: false } }));
    // resolved probation, not confirmed, under K => not persisted
    s.prefixes.set("h/resolved", entry({ nonHtml: 1, probation: { admitted: 3, probeUrl: null, resolved: true } }));
    // unresolved probation but HTML seen => not persisted
    s.prefixes.set("h/probehtml", entry({ nonHtml: 7, sawHtml: true, probation: { admitted: 1, probeUrl: null, resolved: false } }));
    s.isolated.add("https://h/x");
    s.isolated.add("https://h/y");
    assert.equal(
        serializeNonHtmlPrefixState(s),
        '{"version":1,"prefixes":{' +
            '"h/threshold":{"nonHtml":5,"confirmedAt":"2026-01-01T00:00:00.000Z"},' +
            '"h/confirmed":{"nonHtml":1,"confirmedAt":"2026-01-01T00:00:00.000Z"},' +
            '"h/probing":{"nonHtml":7,"confirmedAt":null}' +
            '},"urls":["https://h/x","https://h/y"]}',
    );
});

test("serialize: empty state => exact empty document, no newline, no indentation", () => {
    const out = serializeNonHtmlPrefixState(stateWith());
    assert.equal(out, EMPTY_BYTES);
    assert.equal(out.includes("\n"), false);
    assert.equal(NONHTML_SIDECAR_VERSION, 1);
});

test("serialize: urls = isolated then loadedIsolated, deduplicated, truncated to isolatedMax", () => {
    const s = stateWith(3);
    s.isolated.add("https://h/a");
    s.isolated.add("https://h/b");
    s.loadedIsolated.add("https://h/b"); // duplicate of an isolated entry
    s.loadedIsolated.add("https://h/c");
    s.loadedIsolated.add("https://h/d"); // 4th distinct => cut by isolatedMax=3
    assert.deepEqual(JSON.parse(serializeNonHtmlPrefixState(s)).urls, ["https://h/a", "https://h/b", "https://h/c"]);
});

test("serialize -> parse round trip keeps keys, counts, confirmedAt and urls", () => {
    const s = stateWith();
    s.prefixes.set("h/one", entry({ nonHtml: 6, confirmed: true, confirmedAt: TS }));
    s.prefixes.set("h/two", entry({ nonHtml: 2, probation: { admitted: 0, probeUrl: null, resolved: false } }));
    s.isolated.add("https://h/z");
    const data = parseNonHtmlPrefixSidecar(serializeNonHtmlPrefixState(s));
    assert.deepEqual([...data.prefixes.entries()], [
        ["h/one", { nonHtml: 6, confirmedAt: TS }],
        ["h/two", { nonHtml: 2, confirmedAt: null }],
    ]);
    assert.deepEqual(data.urls, ["https://h/z"]);
});

// -------------------------------------------------------------------- parse

test("parse: null => empty data", () => {
    const d = parseNonHtmlPrefixSidecar(null);
    assert.equal(d.prefixes.size, 0);
    assert.deepEqual(d.urls, []);
});

test("parse: invalid JSON => empty data", () => {
    for (const raw of ["", "{", "not json", '{"version":1,'])
        assert.deepEqual(parseNonHtmlPrefixSidecar(raw), { prefixes: new Map(), urls: [] }, raw);
});

test("parse: non-object JSON (array, number, string, null) => empty data", () => {
    for (const raw of ["[]", "[1,2]", "5", '"x"', "null", "true"])
        assert.deepEqual(parseNonHtmlPrefixSidecar(raw), { prefixes: new Map(), urls: [] }, raw);
});

test("parse: version other than 1 (or missing) => empty data even if the body is valid", () => {
    const body = '"prefixes":{"h/a":{"nonHtml":9,"confirmedAt":null}},"urls":["https://h/x"]';
    for (const raw of [`{"version":2,${body}}`, `{"version":"1",${body}}`, `{"version":0,${body}}`, `{${body}}`])
        assert.deepEqual(parseNonHtmlPrefixSidecar(raw), { prefixes: new Map(), urls: [] }, raw);
});

test("parse: prefixes that is not a plain object => empty prefixes, urls still read", () => {
    for (const p of ["[]", '"x"', "5", "null"]) {
        const d = parseNonHtmlPrefixSidecar(`{"version":1,"prefixes":${p},"urls":["https://h/x"]}`);
        assert.equal(d.prefixes.size, 0, p);
        assert.deepEqual(d.urls, ["https://h/x"], p);
    }
});

test("parse: entry with nonHtml not an integer >= 0 (or not an object) is ignored, valid ones kept", () => {
    const raw = JSON.stringify({
        version: 1,
        prefixes: {
            "h/neg": { nonHtml: -1, confirmedAt: null },
            "h/float": { nonHtml: 1.5, confirmedAt: null },
            "h/str": { nonHtml: "3", confirmedAt: null },
            "h/missing": { confirmedAt: null },
            "h/null": null,
            "h/array": [5],
            "h/zero": { nonHtml: 0, confirmedAt: null },
            "h/ok": { nonHtml: 4, confirmedAt: TS },
        },
        urls: [],
    });
    const d = parseNonHtmlPrefixSidecar(raw);
    assert.deepEqual([...d.prefixes.entries()], [
        ["h/zero", { nonHtml: 0, confirmedAt: null }],
        ["h/ok", { nonHtml: 4, confirmedAt: TS }],
    ]);
});

test("parse: confirmedAt that is not a string => null", () => {
    const raw = JSON.stringify({
        version: 1,
        prefixes: {
            "h/num": { nonHtml: 1, confirmedAt: 12345 },
            "h/obj": { nonHtml: 1, confirmedAt: {} },
            "h/abs": { nonHtml: 1 },
            "h/str": { nonHtml: 1, confirmedAt: TS },
        },
        urls: [],
    });
    const d = parseNonHtmlPrefixSidecar(raw);
    assert.equal(d.prefixes.get("h/num")?.confirmedAt, null);
    assert.equal(d.prefixes.get("h/obj")?.confirmedAt, null);
    assert.equal(d.prefixes.get("h/abs")?.confirmedAt, null);
    assert.equal(d.prefixes.get("h/str")?.confirmedAt, TS);
});

test("parse: urls keeps only non-empty strings; urls absent or not an array => []", () => {
    const raw = JSON.stringify({ version: 1, prefixes: {}, urls: ["https://h/a", "", 5, null, {}, "https://h/b"] });
    assert.deepEqual(parseNonHtmlPrefixSidecar(raw).urls, ["https://h/a", "https://h/b"]);
    assert.deepEqual(parseNonHtmlPrefixSidecar('{"version":1,"prefixes":{}}').urls, []);
    assert.deepEqual(parseNonHtmlPrefixSidecar('{"version":1,"prefixes":{},"urls":"https://h/a"}').urls, []);
});

// ------------------------------------------------------------ loadSidecarInto

const DATA = () => parseNonHtmlPrefixSidecar(JSON.stringify({
    version: 1,
    prefixes: { "h/a": { nonHtml: 6, confirmedAt: TS }, "h/b": { nonHtml: 2, confirmedAt: null } },
    urls: ["https://h/x/", "https://h/y"],
}));

test("loadSidecarInto current: confirmed entries, no probation, count of added keys", () => {
    const s = stateWith(10);
    assert.equal(loadSidecarInto(s, DATA(), "current"), 2);
    assert.deepEqual(s.prefixes.get("h/a"), { nonHtml: 6, sawHtml: false, confirmed: true, confirmedAt: TS, probation: null });
    assert.deepEqual(s.prefixes.get("h/b"), { nonHtml: 2, sawHtml: false, confirmed: true, confirmedAt: null, probation: null });
});

test("loadSidecarInto previous: unconfirmed entries in unresolved probation, admitted 0", () => {
    const s = stateWith(10);
    assert.equal(loadSidecarInto(s, DATA(), "previous"), 2);
    assert.deepEqual(s.prefixes.get("h/a"), {
        nonHtml: 6, sawHtml: false, confirmed: false, confirmedAt: TS,
        probation: { admitted: 0, probeUrl: null, resolved: false },
    });
});

test("loadSidecarInto: a key already in state.prefixes is skipped and not counted", () => {
    const s = stateWith(10);
    const existing = entry({ nonHtml: 99, sawHtml: true });
    s.prefixes.set("h/a", existing);
    assert.equal(loadSidecarInto(s, DATA(), "current"), 1);
    assert.equal(s.prefixes.get("h/a"), existing); // same object, untouched
    assert.equal(s.prefixes.get("h/b")?.confirmed, true);
});

test("loadSidecarInto: urls are normalised (trailing slash) and loadedIsolated is capped at isolatedMax", () => {
    const s = stateWith(10);
    loadSidecarInto(s, DATA(), "current");
    assert.deepEqual([...s.loadedIsolated], ["https://h/x", "https://h/y"]);
    const capped = stateWith(1);
    loadSidecarInto(capped, DATA(), "current");
    assert.deepEqual([...capped.loadedIsolated], ["https://h/x"]);
});

test("loadSidecarInto order: current first, then previous => a key in both stays confirmed, not re-probed", () => {
    const s = stateWith(10);
    const added1 = loadSidecarInto(s, DATA(), "current");
    const added2 = loadSidecarInto(s, DATA(), "previous");
    assert.equal(added1, 2);
    assert.equal(added2, 0);
    assert.equal(s.prefixes.get("h/a")?.confirmed, true);
    assert.equal(s.prefixes.get("h/a")?.probation, null);
});

// -------------------------------------------------------------------- chemins

test("currentSidecarPath: relative path under storage/datasets/<domain>", () => {
    assert.equal(NONHTML_PREFIX_SIDECAR, "__nonhtml_prefixes.json");
    assert.equal(currentSidecarPath("ex.tld"), "storage/datasets/ex.tld/__nonhtml_prefixes.json");
});

const plantPrevious = (tmp: string, dirName: string): string => {
    const dir = path.join(tmp, "prev", "storage", "datasets", dirName);
    fs.mkdirSync(dir, { recursive: true });
    const file = path.join(dir, NONHTML_PREFIX_SIDECAR);
    fs.writeFileSync(file, EMPTY_BYTES);
    return file;
};

test("resolvePreviousSidecarPath: finds the file under the original domain name", () => {
    withTmp((tmp) => {
        const cwd = path.join(tmp, "current");
        fs.mkdirSync(cwd, { recursive: true });
        const file = plantPrevious(tmp, "ex.tld");
        assert.equal(resolvePreviousSidecarPath("prev", "ex.tld", cwd), file);
    });
});

test("resolvePreviousSidecarPath: falls back to the sanitised domain (dots => hyphens)", () => {
    withTmp((tmp) => {
        const cwd = path.join(tmp, "current");
        fs.mkdirSync(cwd, { recursive: true });
        const file = plantPrevious(tmp, "ex-tld");
        assert.equal(resolvePreviousSidecarPath("prev", "ex.tld", cwd), file);
    });
});

test("resolvePreviousSidecarPath: the original name wins when both exist", () => {
    withTmp((tmp) => {
        const cwd = path.join(tmp, "current");
        fs.mkdirSync(cwd, { recursive: true });
        plantPrevious(tmp, "ex-tld");
        const original = plantPrevious(tmp, "ex.tld");
        assert.equal(resolvePreviousSidecarPath("prev", "ex.tld", cwd), original);
    });
});

test("resolvePreviousSidecarPath: absent previous crawl, absent dataset or absent file => null", () => {
    withTmp((tmp) => {
        const cwd = path.join(tmp, "current");
        fs.mkdirSync(cwd, { recursive: true });
        assert.equal(resolvePreviousSidecarPath("nope", "ex.tld", cwd), null);
        fs.mkdirSync(path.join(tmp, "prev", "storage", "datasets", "ex.tld"), { recursive: true }); // dir, no sidecar
        assert.equal(resolvePreviousSidecarPath("prev", "ex.tld", cwd), null);
    });
});

// ------------------------------------------------------------------------ I/O

test("writeSidecarFile: creates missing directories, writes the text, leaves no .tmp", () => {
    withTmp((tmp) => {
        const file = path.join(tmp, "a", "b", NONHTML_PREFIX_SIDECAR);
        writeSidecarFile(file, EMPTY_BYTES);
        assert.equal(fs.readFileSync(file, "utf-8"), EMPTY_BYTES);
        assert.deepEqual(fs.readdirSync(path.dirname(file)), [NONHTML_PREFIX_SIDECAR]);
    });
});

test("writeSidecarFile: a second write replaces the content (no append, no .tmp)", () => {
    withTmp((tmp) => {
        const file = path.join(tmp, NONHTML_PREFIX_SIDECAR);
        writeSidecarFile(file, "first-version-longer-than-second");
        writeSidecarFile(file, "second");
        assert.equal(fs.readFileSync(file, "utf-8"), "second");
        assert.deepEqual(fs.readdirSync(tmp), [NONHTML_PREFIX_SIDECAR]);
    });
});

test("writeSidecarFile: directory cannot be created => console.warn, no throw", () => {
    withTmp((tmp) => {
        const blocker = path.join(tmp, "blocker");
        fs.writeFileSync(blocker, "x"); // a FILE where a directory is needed
        const warn = mock.method(console, "warn", () => {});
        try {
            assert.doesNotThrow(() => writeSidecarFile(path.join(blocker, "sub", NONHTML_PREFIX_SIDECAR), EMPTY_BYTES));
            assert.equal(warn.mock.callCount(), 1);
            assert.match(String(warn.mock.calls[0].arguments[0]), /^\[nonhtml-prefix\] sidecar write failed: /);
        } finally {
            warn.mock.restore();
        }
    });
});

test("writeSidecarFile: rename fails (target is a directory) => console.warn, no throw, no .tmp left", () => {
    withTmp((tmp) => {
        const file = path.join(tmp, NONHTML_PREFIX_SIDECAR);
        fs.mkdirSync(file); // target path is a directory: renameSync(tmp, file) must fail
        const warn = mock.method(console, "warn", () => {});
        try {
            assert.doesNotThrow(() => writeSidecarFile(file, EMPTY_BYTES));
            assert.equal(warn.mock.callCount(), 1);
            assert.match(String(warn.mock.calls[0].arguments[0]), /^\[nonhtml-prefix\] sidecar write failed: /);
            assert.equal(fs.existsSync(`${file}.tmp`), false);
        } finally {
            warn.mock.restore();
        }
    });
});

test("readSidecarFile(null) => null", () => {
    assert.equal(readSidecarFile(null), null);
});

test("readSidecarFile: absent file or unreadable path (a directory) => null", () => {
    withTmp((tmp) => {
        assert.equal(readSidecarFile(path.join(tmp, "absent.json")), null);
        assert.equal(readSidecarFile(tmp), null); // reading a directory throws EISDIR => null
    });
});

test("readSidecarFile: returns the exact text written by writeSidecarFile", () => {
    withTmp((tmp) => {
        const file = path.join(tmp, "x", NONHTML_PREFIX_SIDECAR);
        writeSidecarFile(file, EMPTY_BYTES);
        assert.equal(readSidecarFile(file), EMPTY_BYTES);
    });
});

// ------------------------------------------- R23 I-2: isolated URL probation (load, serialize)

const URLS = (urls: string[]) => parseNonHtmlPrefixSidecar(JSON.stringify({ version: 1, prefixes: {}, urls }));

test("loadSidecarInto previous (I-2): urls go to isolatedProbation (normalised), not to loadedIsolated", () => {
    const s = stateWith(10);
    loadSidecarInto(s, DATA(), "previous");
    assert.deepEqual([...s.isolatedProbation], ["https://h/x", "https://h/y"]);
    assert.equal(s.loadedIsolated.size, 0);
});

test("loadSidecarInto current (I-2): urls go to loadedIsolated, isolatedProbation stays empty", () => {
    const s = stateWith(10);
    loadSidecarInto(s, DATA(), "current");
    assert.deepEqual([...s.loadedIsolated], ["https://h/x", "https://h/y"]);
    assert.equal(s.isolatedProbation.size, 0);
});

test("loadSidecarInto order (I-2): current then previous => a URL in both stays in loadedIsolated, new ones go to probation", () => {
    const s = stateWith(10);
    loadSidecarInto(s, DATA(), "current");
    loadSidecarInto(s, URLS(["https://h/y/", "https://h/z"]), "previous");
    assert.deepEqual([...s.loadedIsolated], ["https://h/x", "https://h/y"]);
    assert.deepEqual([...s.isolatedProbation], ["https://h/z"]);
});

test("loadSidecarInto (I-2): the cap is loadedIsolated + isolatedProbation combined", () => {
    const s = stateWith(3);
    loadSidecarInto(s, DATA(), "current");
    loadSidecarInto(s, URLS(["https://h/a", "https://h/b", "https://h/c"]), "previous");
    assert.deepEqual([...s.loadedIsolated], ["https://h/x", "https://h/y"]);
    assert.deepEqual([...s.isolatedProbation], ["https://h/a"]);
    const p = stateWith(1);
    loadSidecarInto(p, DATA(), "previous");
    assert.deepEqual([...p.isolatedProbation], ["https://h/x"]);
});

test("serialize (I-2): urls = isolated, loadedIsolated, then isolatedProbation, deduplicated, truncated", () => {
    const s = stateWith(4);
    s.isolated.add("https://h/a");
    s.loadedIsolated.add("https://h/b");
    s.isolatedProbation.add("https://h/a"); // duplicate
    s.isolatedProbation.add("https://h/c");
    s.isolatedProbation.add("https://h/d");
    s.isolatedProbation.add("https://h/e"); // 5th distinct => cut by isolatedMax=4
    assert.deepEqual(JSON.parse(serializeNonHtmlPrefixState(s)).urls,
        ["https://h/a", "https://h/b", "https://h/c", "https://h/d"]);
});

test("serialize (I-2): an unresolved probation round-trips to the next crawl's probation", () => {
    const s = stateWith(10);
    loadSidecarInto(s, DATA(), "previous");
    const next = stateWith(10);
    loadSidecarInto(next, parseNonHtmlPrefixSidecar(serializeNonHtmlPrefixState(s)), "previous");
    assert.deepEqual([...next.isolatedProbation], ["https://h/x", "https://h/y"]);
});
