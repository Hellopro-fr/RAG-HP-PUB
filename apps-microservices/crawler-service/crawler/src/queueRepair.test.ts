import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import { recountQueueFromDisk, repairQueueMetadata } from "./queueRepair.js";

function mkQueue(files: Record<string, unknown>): string {
    const dir = fs.mkdtempSync(`${os.tmpdir()}/rqtest-`);
    for (const [name, content] of Object.entries(files)) {
        fs.writeFileSync(`${dir}/${name}`, typeof content === "string" ? content : JSON.stringify(content));
    }
    return dir;
}
const rm = (d: string) => fs.rmSync(d, { recursive: true, force: true });

test("recountQueueFromDisk: all handled (orderNo null)", () => {
    const dir = mkQueue({
        "a.json": { id: "a", orderNo: null, url: "x" },
        "b.json": { id: "b", orderNo: null, url: "y" },
        "__metadata__.json": { pendingRequestCount: 0, handledRequestCount: 0 },
    });
    assert.deepEqual(recountQueueFromDisk(dir), { pending: 0, handled: 2, total: 2 });
    rm(dir);
});

test("recountQueueFromDisk: mixed pending/handled (positive + forefront negative orderNo = pending)", () => {
    const dir = mkQueue({
        "a.json": { orderNo: null },
        "b.json": { orderNo: 1764681450508 },
        "c.json": { orderNo: -1764681450508 },
    });
    assert.deepEqual(recountQueueFromDisk(dir), { pending: 2, handled: 1, total: 3 });
    rm(dir);
});

test("recountQueueFromDisk: excludes __metadata__/dotfiles/non-json; skips unparseable", () => {
    const dir = mkQueue({
        "a.json": { orderNo: null },
        "__metadata__.json": { foo: 1 },
        ".DS_Store": "x",
        "notes.txt": "x",
        "bad.json": "{not valid json",
    });
    assert.deepEqual(recountQueueFromDisk(dir), { pending: 0, handled: 1, total: 1 });
    rm(dir);
});

test("recountQueueFromDisk: missing dir → zeros", () => {
    assert.deepEqual(recountQueueFromDisk(`${os.tmpdir()}/no-such-rqtest-zzz-xyz`), { pending: 0, handled: 0, total: 0 });
});

test("recountQueueFromDisk: malformed orderNo (missing) counts as handled (stall-proof)", () => {
    const dir = mkQueue({ "a.json": { id: "a", url: "x" } });
    assert.deepEqual(recountQueueFromDisk(dir), { pending: 0, handled: 1, total: 1 });
    rm(dir);
});

test("repairQueueMetadata: stale 0/0 with 1 handled file → rewrites to 0/1, before captured", () => {
    const dir = mkQueue({
        "a.json": { orderNo: null },
        "__metadata__.json": { id: "d", name: "d", pendingRequestCount: 0, handledRequestCount: 0, createdAt: "t", forefrontRequestIds: [] },
    });
    const res = repairQueueMetadata(dir);
    assert.equal(res.repaired, true);
    assert.deepEqual(res.before, { pending: 0, handled: 0, total: 1 });
    const meta = JSON.parse(fs.readFileSync(`${dir}/__metadata__.json`, "utf-8"));
    assert.equal(meta.pendingRequestCount, 0);
    assert.equal(meta.handledRequestCount, 1);
    assert.equal(meta.id, "d");
    assert.deepEqual(meta.forefrontRequestIds, []);
    rm(dir);
});

test("repairQueueMetadata: sum-correct but split-wrong → repaired", () => {
    const dir = mkQueue({
        "a.json": { orderNo: null },
        "__metadata__.json": { pendingRequestCount: 1, handledRequestCount: 0, forefrontRequestIds: [] },
    });
    const res = repairQueueMetadata(dir);
    assert.equal(res.repaired, true);
    const meta = JSON.parse(fs.readFileSync(`${dir}/__metadata__.json`, "utf-8"));
    assert.equal(meta.pendingRequestCount, 0);
    assert.equal(meta.handledRequestCount, 1);
    rm(dir);
});

test("repairQueueMetadata: consistent metadata → no-op (file untouched)", () => {
    const dir = mkQueue({
        "a.json": { orderNo: 123 },
        "__metadata__.json": { pendingRequestCount: 1, handledRequestCount: 0, forefrontRequestIds: [] },
    });
    const before = fs.readFileSync(`${dir}/__metadata__.json`, "utf-8");
    const res = repairQueueMetadata(dir);
    assert.equal(res.repaired, false);
    assert.equal(fs.readFileSync(`${dir}/__metadata__.json`, "utf-8"), before);
    rm(dir);
});

test("repairQueueMetadata: missing metadata + files → constructs it, before=null", () => {
    const dir = mkQueue({ "a.json": { orderNo: null } });
    const res = repairQueueMetadata(dir);
    assert.equal(res.repaired, true);
    assert.equal(res.before, null);
    const meta = JSON.parse(fs.readFileSync(`${dir}/__metadata__.json`, "utf-8"));
    assert.equal(meta.handledRequestCount, 1);
    assert.equal(meta.pendingRequestCount, 0);
    rm(dir);
});

test("repairQueueMetadata: empty dir → no-op, no metadata written", () => {
    const dir = fs.mkdtempSync(`${os.tmpdir()}/rqtest-`);
    const res = repairQueueMetadata(dir);
    assert.equal(res.repaired, false);
    assert.equal(fs.existsSync(`${dir}/__metadata__.json`), false);
    rm(dir);
});
