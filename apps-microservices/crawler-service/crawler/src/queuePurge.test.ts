import { test } from "node:test";
import assert from "node:assert/strict";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { flagStaleVariantsOnDisk } from "./queuePurge.js";

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
