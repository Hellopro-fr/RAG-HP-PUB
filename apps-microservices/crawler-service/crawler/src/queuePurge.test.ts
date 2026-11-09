import { test } from "node:test";
import assert from "node:assert/strict";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { flagStaleVariantsOnDisk, queuePurgeMarkHandledEnabled } from "./queuePurge.js";
import { recountQueueFromDisk } from "./queueRepair.js";

// fake strip: drop a ?ref= param -> base
const stripFn = (u: string) => u.replace(/\?ref=[^&]*$/, "");

function writeReq(dir: string, name: string, url: string, orderNo: number | null) {
    const obj = { id: name, url, uniqueKey: url, orderNo, json: JSON.stringify({ url, uniqueKey: url }) };
    fs.writeFileSync(path.join(dir, `${name}.json`), JSON.stringify(obj));
}

test("flags a pending variant whose stripped base is a handled file; leaves keeper + handled alone", () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "qp-"));
    writeReq(dir, "handled_base", "https://x.fr/p", null);
    writeReq(dir, "pending_variant", "https://x.fr/p?ref=1", 2);
    writeReq(dir, "pending_other", "https://x.fr/q", 3);
    fs.writeFileSync(path.join(dir, "__metadata__.json"), "{}");

    const res = flagStaleVariantsOnDisk(dir, stripFn);
    assert.equal(res.flagged, 1);

    const variant = JSON.parse(fs.readFileSync(path.join(dir, "pending_variant.json"), "utf-8"));
    assert.equal(variant.userData?.__crawlee?.skipNavigation, true);
    assert.equal(JSON.parse(variant.json).userData?.__crawlee?.skipNavigation, true);
    assert.equal(variant.orderNo, 2, "orderNo must not change");

    const other = JSON.parse(fs.readFileSync(path.join(dir, "pending_other.json"), "utf-8"));
    assert.equal(other.userData?.__crawlee?.skipNavigation, undefined);
});

test("keeps one copy when no handled canonical exists (loss-proof)", () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "qp-"));
    writeReq(dir, "v1", "https://x.fr/p?ref=1", 1);
    writeReq(dir, "v2", "https://x.fr/p?ref=2", 2);
    const res = flagStaleVariantsOnDisk(dir, stripFn);
    assert.equal(res.flagged, 1, "one kept, one flagged");
    assert.equal(res.kept, 1);
});

test("skips unparseable files without throwing", () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "qp-"));
    fs.writeFileSync(path.join(dir, "broken.json"), "{ not valid json");
    writeReq(dir, "handled_base", "https://x.fr/p", null);
    writeReq(dir, "pending_variant", "https://x.fr/p?ref=1", 2);
    const res = flagStaleVariantsOnDisk(dir, stripFn);
    assert.equal(res.flagged, 1, "unparseable ignored, real variant still flagged");
});

test("no-op when nothing strips (no committed decision collapses anything)", () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "qp-"));
    writeReq(dir, "a", "https://x.fr/p", null);
    writeReq(dir, "b", "https://x.fr/q", 1);
    writeReq(dir, "c", "https://x.fr/r", 2);
    const res = flagStaleVariantsOnDisk(dir, stripFn); // stripFn leaves these unchanged
    assert.equal(res.flagged, 0);
    const b = JSON.parse(fs.readFileSync(path.join(dir, "b.json"), "utf-8"));
    assert.equal(b.userData?.__crawlee?.skipNavigation, undefined);
});

// ---------------------------------------------------------------------------
// A517 Brief 2 — QUEUE_PURGE_MARK_HANDLED_ENABLED (startup purge writes variants handled)
// ---------------------------------------------------------------------------

const MARK_ENV = "QUEUE_PURGE_MARK_HANDLED_ENABLED";

/** Run fn with the flag set to `value` (undefined = absent), then restore the env. */
function withFlag<T>(value: string | undefined, fn: () => T): T {
    const saved = process.env[MARK_ENV];
    if (value === undefined) delete process.env[MARK_ENV]; else process.env[MARK_ENV] = value;
    try {
        return fn();
    } finally {
        if (saved === undefined) delete process.env[MARK_ENV]; else process.env[MARK_ENV] = saved;
    }
}

/** A pending request already flagged skipNavigation by a previous start (root + inner json). */
function writeFlaggedReq(dir: string, name: string, url: string, orderNo: number) {
    const inner = { url, uniqueKey: url, userData: { __crawlee: { skipNavigation: true } } };
    const obj = { id: name, url, uniqueKey: url, orderNo, json: JSON.stringify(inner), userData: { __crawlee: { skipNavigation: true } } };
    fs.writeFileSync(path.join(dir, `${name}.json`), JSON.stringify(obj, null, 2));
}

/** One queue with every case: handled base, flagged variant, keeper, previously flagged, broken file. */
function writeMixedQueue(dir: string) {
    writeReq(dir, "handled_base", "https://x.fr/p", null);
    writeReq(dir, "pending_variant", "https://x.fr/p?ref=1", 2);
    writeReq(dir, "pending_other", "https://x.fr/q", 3);
    writeFlaggedReq(dir, "pending_old_flag", "https://x.fr/r?ref=9", 4);
    fs.writeFileSync(path.join(dir, "broken.json"), "{ not valid json");
    fs.writeFileSync(path.join(dir, "__metadata__.json"), "{}");
}

const readDir = (dir: string): Record<string, string> =>
    Object.fromEntries(fs.readdirSync(dir).sort().map((n) => [n, fs.readFileSync(path.join(dir, n), "utf-8")]));

const readJson = (dir: string, name: string): any => JSON.parse(fs.readFileSync(path.join(dir, `${name}.json`), "utf-8"));

/** The purge as it stood before A517 Brief 2 (queuePurge.ts @ e3e44baaa), copied verbatim. */
const legacyIsPending = (orderNo: unknown): boolean =>
    typeof orderNo === "number" && Number.isFinite(orderNo);
const legacyFlagStaleVariantsOnDisk = (
    queueDir: string,
    stripFn: (url: string) => string,
    extraSkip?: (url: string) => boolean,
): { flagged: number; kept: number } => {
    let flagged = 0;
    let kept = 0;
    let names: string[];
    try {
        names = fs.readdirSync(queueDir);
    } catch {
        return { flagged, kept };
    }
    type Rec = { file: string; obj: any };
    const pending: Rec[] = [];
    const canonical = new Set<string>();
    for (const name of names) {
        if (!name.endsWith(".json") || name === "__metadata__.json" || name.startsWith(".")) continue;
        const file = path.join(queueDir, name);
        let obj: any;
        try {
            obj = JSON.parse(fs.readFileSync(file, "utf-8"));
        } catch {
            continue;
        }
        if (legacyIsPending(obj.orderNo)) {
            pending.push({ file, obj });
        } else {
            try { canonical.add(stripFn(obj.url)); } catch { /* skip */ }
        }
    }
    for (const { file, obj } of pending) {
        let stripped: string;
        try { stripped = stripFn(obj.url); } catch { kept++; continue; }
        const staleByExtra = Boolean(extraSkip && extraSkip(obj.url));
        if ((stripped !== obj.url && canonical.has(stripped)) || staleByExtra) {
            obj.userData = obj.userData ?? {};
            obj.userData.__crawlee = obj.userData.__crawlee ?? {};
            obj.userData.__crawlee.skipNavigation = true;
            try {
                const inner = JSON.parse(obj.json);
                inner.userData = inner.userData ?? {};
                inner.userData.__crawlee = inner.userData.__crawlee ?? {};
                inner.userData.__crawlee.skipNavigation = true;
                obj.json = JSON.stringify(inner);
            } catch { /* inner missing/malformed: root flag still applies */ }
            fs.writeFileSync(file, JSON.stringify(obj, null, 2));
            flagged++;
        } else {
            canonical.add(stripped);
            kept++;
        }
    }
    return { flagged, kept };
};

test("A517 flag OFF (absent or \"false\"): files byte-identical to the legacy purge, markedHandled 0, no callback", () => {
    for (const value of [undefined, "false"]) {
        const legacyDir = fs.mkdtempSync(path.join(os.tmpdir(), "qp-legacy-"));
        const newDir = fs.mkdtempSync(path.join(os.tmpdir(), "qp-new-"));
        writeMixedQueue(legacyDir);
        writeMixedQueue(newDir);
        const legacy = legacyFlagStaleVariantsOnDisk(legacyDir, stripFn);
        const calls: string[] = [];
        const res = withFlag(value, () => flagStaleVariantsOnDisk(newDir, stripFn, undefined, (u) => { calls.push(u); }));
        assert.deepEqual(readDir(newDir), readDir(legacyDir), `flag ${value}: same files, same bytes`);
        assert.equal(res.flagged, legacy.flagged);
        assert.equal(res.kept, legacy.kept);
        assert.equal(res.markedHandled, 0);
        assert.deepEqual(calls, []);
    }
});

test("A517 flag ON: flagged variants written handled (orderNo null + handledAt), keeper untouched, recount pending = kept", () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "qp-on-"));
    writeReq(dir, "handled_base", "https://x.fr/p", null);
    writeReq(dir, "pending_variant", "https://x.fr/p?ref=1", 2);
    writeReq(dir, "pending_variant2", "https://x.fr/p?ref=2", 5);
    writeReq(dir, "pending_other", "https://x.fr/q", 3);
    const otherBefore = fs.readFileSync(path.join(dir, "pending_other.json"), "utf-8");
    const calls: string[] = [];
    const res = withFlag("true", () => flagStaleVariantsOnDisk(dir, stripFn, undefined, (u) => { calls.push(u); }));
    assert.equal(res.flagged, 2);
    assert.equal(res.kept, 1);
    assert.equal(res.markedHandled, 2);
    for (const name of ["pending_variant", "pending_variant2"]) {
        const v = readJson(dir, name);
        assert.equal(v.orderNo, null, `${name}: handled at the root`);
        const inner = JSON.parse(v.json);
        assert.equal(typeof inner.handledAt, "string");
        assert.ok(!Number.isNaN(Date.parse(inner.handledAt)), `${name}: handledAt is a date`);
        assert.equal(inner.userData?.__crawlee?.skipNavigation, true, `${name}: still flagged (the routes.ts guard stays valid)`);
    }
    assert.equal(fs.readFileSync(path.join(dir, "pending_other.json"), "utf-8"), otherBefore, "keeper byte-identical");
    assert.deepEqual(recountQueueFromDisk(dir), { pending: 1, handled: 3, total: 4 });
    assert.deepEqual(calls.sort(), ["https://x.fr/p?ref=1", "https://x.fr/p?ref=2"]);
});

test("A517 flag ON (R2): a request already flagged by a previous start is converted and stays OUT of canonical, so a later variant of the same base is kept (conservative)", () => {
    // No handled file anchors https://x.fr/p. Flag off, the old-flagged request is kept or
    // re-flagged and one of the two anchors the other. Flag on, the old-flagged one is
    // converted without entering canonical, so pending_v2 is kept: fetched once, deduped live.
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "qp-r2-"));
    writeFlaggedReq(dir, "pending_old_flag", "https://x.fr/p?ref=1", 1);
    writeReq(dir, "pending_v2", "https://x.fr/p?ref=2", 2);
    const v2Before = fs.readFileSync(path.join(dir, "pending_v2.json"), "utf-8");
    const calls: string[] = [];
    const res = withFlag("true", () => flagStaleVariantsOnDisk(dir, stripFn, undefined, (u) => { calls.push(u); }));
    assert.equal(res.markedHandled, 1);
    assert.equal(res.flagged, 0);
    assert.equal(res.kept, 1, "pending_v2 kept: nothing anchors its base");
    const old = readJson(dir, "pending_old_flag");
    assert.equal(old.orderNo, null);
    assert.equal(typeof JSON.parse(old.json).handledAt, "string");
    assert.equal(fs.readFileSync(path.join(dir, "pending_v2.json"), "utf-8"), v2Before, "pending_v2 untouched");
    assert.deepEqual(recountQueueFromDisk(dir), { pending: 1, handled: 1, total: 2 });
    assert.deepEqual(calls, ["https://x.fr/p?ref=1"]);

    // Same queue, flag off: the previous outcome (one flagged, one kept).
    const off = fs.mkdtempSync(path.join(os.tmpdir(), "qp-r2-off-"));
    writeFlaggedReq(off, "pending_old_flag", "https://x.fr/p?ref=1", 1);
    writeReq(off, "pending_v2", "https://x.fr/p?ref=2", 2);
    const resOff = withFlag(undefined, () => flagStaleVariantsOnDisk(off, stripFn));
    assert.equal(resOff.flagged, 1);
    assert.equal(resOff.kept, 1);
    assert.equal(resOff.markedHandled, 0);
});

test("A517 flag ON: a throwing onMarkedHandled never blocks the purge", () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "qp-cb-"));
    writeReq(dir, "handled_base", "https://x.fr/p", null);
    writeReq(dir, "pending_variant", "https://x.fr/p?ref=1", 2);
    const res = withFlag("true", () => flagStaleVariantsOnDisk(dir, stripFn, undefined, () => { throw new Error("boom"); }));
    assert.equal(res.markedHandled, 1);
    assert.equal(readJson(dir, "pending_variant").orderNo, null);
});

test("A517 flag read at call time (not memoized)", () => {
    assert.equal(withFlag("true", () => queuePurgeMarkHandledEnabled()), true);
    assert.equal(withFlag("TRUE", () => queuePurgeMarkHandledEnabled()), true);
    assert.equal(withFlag("false", () => queuePurgeMarkHandledEnabled()), false);
    assert.equal(withFlag(undefined, () => queuePurgeMarkHandledEnabled()), false);
    const on = fs.mkdtempSync(path.join(os.tmpdir(), "qp-call-on-"));
    const off = fs.mkdtempSync(path.join(os.tmpdir(), "qp-call-off-"));
    for (const dir of [on, off]) {
        writeReq(dir, "handled_base", "https://x.fr/p", null);
        writeReq(dir, "pending_variant", "https://x.fr/p?ref=1", 2);
    }
    assert.equal(withFlag("true", () => flagStaleVariantsOnDisk(on, stripFn)).markedHandled, 1);
    assert.equal(withFlag("false", () => flagStaleVariantsOnDisk(off, stripFn)).markedHandled, 0);
    assert.equal(readJson(off, "pending_variant").orderNo, 2);
});
