import { test } from "node:test";
import assert from "node:assert/strict";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import {
    buildReplayRows,
    extractRecords,
    formatReport,
    main,
    replayAll,
    replayForK,
} from "./nonHtmlPrefixReplay.js";

const rec = (url: string, mtime: string, file = "000000001.json") => ({ file, size_bytes: 1, mtime, url });
const T = (s: string) => `2026-01-01T00:00:${s}`;

// Replay order = mtime ascending: a1..a6 (01-06), x.pdf (06.500), page (07), d1 (08), p1 (10).
const pdfExport = {
    kind: "pdf",
    total_records: 8,
    offset: 0,
    returned: 8,
    records: [
        rec("https://h.test/image/a1", T("01")),
        rec("https://h.test/image/a2", T("02")),
        rec("https://h.test/image/a3", T("03")),
        rec("https://h.test/image/a4", T("04")),
        rec("https://h.test/image/a5", T("05")),
        rec("https://h.test/image/a6", T("06")),
        rec("https://h.test/image/x.pdf", T("06.500")),
        rec("https://h.test/dl?id=1", T("08")),
    ].reverse(), // the endpoint serves newest first
};
const mainExport = {
    kind: "main",
    records: [rec("https://h.test/produits/p1", T("10")), rec("https://h.test/image/page", T("07"))],
};

test("extractRecords accepts a page object, a bare array and an array of pages; drops rows without url", () => {
    const r = rec("https://h.test/a", T("01"));
    assert.equal(extractRecords({ records: [r, { file: "f" }, { url: "" }] }).length, 1);
    assert.equal(extractRecords([r, r]).length, 2);
    assert.equal(extractRecords([{ records: [r] }, { records: [r, r] }]).length, 3);
    assert.deepEqual(extractRecords("nope"), []);
    assert.deepEqual(extractRecords(null), []);
});

test("buildReplayRows orders by mtime, then non-HTML before HTML, then file", () => {
    const rows = buildReplayRows(
        [rec("https://h.test/n2", T("02"), "000000002.json"), rec("https://h.test/n1", T("01"))],
        [rec("https://h.test/h1", T("02"), "000000000.json"), rec("https://h.test/h0", T("00"))],
    );
    assert.deepEqual(
        rows.map((r) => `${r.kind}:${r.url.slice(-2)}`),
        ["html:h0", "nonhtml:n1", "nonhtml:n2", "html:h1"],
    );
});

test("replayForK K=3: learns the key once, releases it on the HTML page, counts the avoided URLs", () => {
    const rows = buildReplayRows(extractRecords(pdfExport), extractRecords(mainExport));
    const r = replayForK(rows, 3);
    assert.equal(r.k, 3);
    assert.equal(r.keysLearned, 1);
    assert.equal(r.keysReleased, 1);
    assert.equal(r.avoidedNonHtml, 3); // a4, a5, a6 — x.pdf excluded (ignored extension)
    assert.equal(r.htmlBlocked, 1); // /image/page seen under a blocking key
    assert.equal(r.isolated, 3); // a1, a2 (under K) + d1 (no parent folder)
    assert.equal(r.nonHtmlRows, 8);
    assert.equal(r.htmlRows, 2);
});

test("replayForK K=1 avoids more, K=7 never learns", () => {
    const rows = buildReplayRows(extractRecords(pdfExport), extractRecords(mainExport));
    const k1 = replayForK(rows, 1);
    assert.equal(k1.keysLearned, 1);
    assert.equal(k1.avoidedNonHtml, 5);
    assert.equal(k1.isolated, 1);
    const k7 = replayForK(rows, 7);
    assert.equal(k7.keysLearned, 0);
    assert.equal(k7.keysReleased, 0);
    assert.equal(k7.avoidedNonHtml, 0);
    assert.equal(k7.htmlBlocked, 0);
    assert.equal(k7.isolated, 7);
});

test("an ignored-extension non-HTML URL is never counted as avoided", () => {
    const rows = buildReplayRows(
        [
            rec("https://h.test/image/a1", T("01")),
            rec("https://h.test/image/a2", T("02")),
            rec("https://h.test/image/b.png", T("03")),
        ],
        [],
    );
    const r = replayForK(rows, 2);
    assert.equal(r.keysLearned, 1);
    assert.equal(r.avoidedNonHtml, 0);
});

test("replayAll covers K=1..10 and the learned count never grows with K", () => {
    const rows = buildReplayRows(extractRecords(pdfExport), extractRecords(mainExport));
    const all = replayAll(rows);
    assert.deepEqual(all.map((r) => r.k), [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]);
    for (let i = 1; i < all.length; i++) {
        assert.ok(all[i].keysLearned <= all[i - 1].keysLearned);
        assert.ok(all[i].avoidedNonHtml <= all[i - 1].avoidedNonHtml);
    }
    assert.equal(all[5].avoidedNonHtml, 0); // K=6: a6 itself crosses the threshold
});

test("formatReport prints a header and one line per K", () => {
    const rows = buildReplayRows(extractRecords(pdfExport), extractRecords(mainExport));
    const text = formatReport(replayAll(rows));
    const lines = text.trimEnd().split("\n");
    assert.match(lines[0], /^K\s+learned\s+released\s+avoided\s+html_blocked\s+isolated$/);
    assert.equal(lines.length, 11);
    assert.match(text, /^\s*3\s+1\s+1\s+3\s+1\s+3\s*$/m);
});

function capture(fn: () => number): { code: number; out: string; err: string } {
    const log = console.log;
    const error = console.error;
    let out = "";
    let err = "";
    console.log = (...a: unknown[]) => { out += a.join(" ") + "\n"; };
    console.error = (...a: unknown[]) => { err += a.join(" ") + "\n"; };
    try {
        return { code: fn(), out, err };
    } finally {
        console.log = log;
        console.error = error;
    }
}

test("main: missing arguments => usage on stderr and code 2", () => {
    const r = capture(() => main([]));
    assert.equal(r.code, 2);
    assert.match(r.err, /Usage:/);
    assert.equal(capture(() => main(["only-one.json"])).code, 2);
});

test("main: unreadable or invalid file => code 1", () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "nhr-"));
    try {
        const bad = path.join(dir, "bad.json");
        fs.writeFileSync(bad, "{not json");
        assert.equal(capture(() => main([path.join(dir, "absent.json"), bad])).code, 1);
        assert.equal(capture(() => main([bad, bad])).code, 1);
    } finally {
        fs.rmSync(dir, { recursive: true, force: true });
    }
});

test("main: valid exports => code 0 and the K table on stdout", () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "nhr-"));
    try {
        const pdf = path.join(dir, "pdf.json");
        const mainFile = path.join(dir, "main.json");
        fs.writeFileSync(pdf, JSON.stringify(pdfExport));
        fs.writeFileSync(mainFile, JSON.stringify(mainExport));
        const r = capture(() => main([pdf, mainFile]));
        assert.equal(r.code, 0);
        assert.match(r.out, /^\s*3\s+1\s+1\s+3\s+1\s+3\s*$/m);
        assert.equal(r.err, "");
    } finally {
        fs.rmSync(dir, { recursive: true, force: true });
    }
});
