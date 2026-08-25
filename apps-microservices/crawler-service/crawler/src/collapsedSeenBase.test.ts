import { test } from "node:test";
import assert from "node:assert/strict";
import { selectSeenBaseRows } from "./collapsedSeenBase.js";

const row = (origin: string, gate = "prenav") => ({
    collapsed: "https://x.fr/p?cat=1", base: "https://x.fr/p", param: "cat", origin, gate,
});

test("selectSeenBaseRows keeps filter_on_seen only", () => {
    const out = selectSeenBaseRows([row("filter_on_seen"), row("facet_cap"), row("qm_strip")]);
    assert.equal(out.length, 1);
    assert.equal(out[0].origin, "filter_on_seen");
});

test("selectSeenBaseRows excludes facet_cap — its base was never verified", () => {
    assert.deepEqual(selectSeenBaseRows([row("facet_cap")]), []);
});

test("selectSeenBaseRows excludes qm_strip — content-proven, different mechanism", () => {
    assert.deepEqual(selectSeenBaseRows([row("qm_strip")]), []);
});

test("selectSeenBaseRows drops a degenerate row defensively", () => {
    const r = { ...row("filter_on_seen"), base: "https://x.fr/p?cat=1" };
    assert.deepEqual(selectSeenBaseRows([r]), []);
});
