import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { clearDecisionSidecars } from "./functions.js";

test("clearDecisionSidecars: removes diez/QM sidecars, keeps others, idempotent", () => {
    const dir = path.join("storage", "test-clear-sidecars");
    fs.rmSync(dir, { recursive: true, force: true });
    fs.mkdirSync(dir, { recursive: true });
    const sidecars = ["_diez_decision.json", "_diez_audit.json", "_questionmark_decision.json", "_questionmark_observations.json"];
    for (const f of sidecars) fs.writeFileSync(path.join(dir, f), "{}");
    // unrelated files that MUST survive
    fs.writeFileSync(path.join(dir, "_callback_payload.json"), "{}");
    fs.writeFileSync(path.join(dir, "_completion_marker.json"), "{}");
    try {
        const removed = clearDecisionSidecars(dir).sort();
        assert.deepEqual(removed, [...sidecars].sort());
        for (const f of sidecars) assert.ok(!fs.existsSync(path.join(dir, f)), `${f} should be gone`);
        assert.ok(fs.existsSync(path.join(dir, "_callback_payload.json")), "callback payload must survive");
        assert.ok(fs.existsSync(path.join(dir, "_completion_marker.json")), "completion marker must survive");
        // idempotent: second call removes nothing
        assert.deepEqual(clearDecisionSidecars(dir), []);
    } finally {
        fs.rmSync(dir, { recursive: true, force: true });
    }
});
