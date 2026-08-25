import { test } from "node:test";
import assert from "node:assert/strict";
import type { JsonlWriter } from "./class/JsonlWriter.js";
import { context } from "./context.js";
import { COLLAPSED_SEEN_BASE_FILE, selectSeenBaseRows, writeCollapsedSeenBase } from "./collapsedSeenBase.js";
import type { CollapseOrigin, CollapseGate } from "./qmConsumptionSkip.js";

const row = (origin: CollapseOrigin, gate: CollapseGate = "prenav") => ({
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

// The exact-equality case above never exercises foldSlash (both strings are byte-identical
// already, `!==` on the raw strings would drop it just as well). foldSlash only strips a
// trailing '/', so the fold is only exercised when collapsed and base carry no other
// difference (no query) — the real-world shape is qmConsumptionSkip's own D1 dequeue path,
// mirrored by qmConsumptionSkip.test.ts's "folds the trailing slash" case.
test("selectSeenBaseRows drops a row that differs from its base only by a trailing slash", () => {
    const r = { ...row("filter_on_seen"), collapsed: "https://x.fr/p/", base: "https://x.fr/p" };
    assert.deepEqual(selectSeenBaseRows([r]), []);
});

// --- writeCollapsedSeenBase: I/O branches (stub JsonlWriter, no real file system) ---

const TS = "2026-08-25T00:00:00.000Z";

type StubLine = { filename: string; data: Record<string, unknown> };

/** Minimal writer shape — only writeLine, cast past JsonlWriter's private fields like the
 * codebase's other `as unknown as <Class>` stubs (e.g. UrlConsolidator.test.ts). */
const stubWriter = () => {
    const lines: StubLine[] = [];
    const writer = {
        writeLine: async (filename: string, data: object) => {
            lines.push({ filename, data: data as Record<string, unknown> });
        },
    } as unknown as JsonlWriter;
    return { writer, lines };
};

const reset = () => {
    context.jsonlWriter = null;
    context.qmCollapsed = [];
    context.qmCollapsedRejected = 0;
};

test("writeCollapsedSeenBase is a no-op outside update mode (no jsonlWriter)", async () => {
    reset();
    context.qmCollapsed = [row("filter_on_seen")];
    context.qmCollapsedRejected = 40;
    assert.equal(await writeCollapsedSeenBase(TS), 0);
});

test("writeCollapsedSeenBase writes one line per admitted row plus a summary", async () => {
    reset();
    const { writer, lines } = stubWriter();
    context.jsonlWriter = writer;
    context.qmCollapsed = [row("filter_on_seen"), row("facet_cap")];

    const written = await writeCollapsedSeenBase(TS);

    assert.equal(written, 1);
    assert.equal(lines.length, 2);
    assert.equal(lines[0].filename, COLLAPSED_SEEN_BASE_FILE);
    assert.deepEqual(lines[0].data, {
        url: "https://x.fr/p?cat=1", base: "https://x.fr/p", param: "cat",
        origin: "filter_on_seen", gate: "prenav", timestamp: TS,
    });
    assert.deepEqual(lines[1].data, { summary: true, written: 1, truncated_by_cap: 0, timestamp: TS });
});

test("writeCollapsedSeenBase still writes the summary at zero admitted rows when the cap refused entries", async () => {
    reset();
    const { writer, lines } = stubWriter();
    context.jsonlWriter = writer;
    context.qmCollapsed = [row("facet_cap")]; // excluded -> 0 admitted
    context.qmCollapsedRejected = 40;

    const written = await writeCollapsedSeenBase(TS);

    assert.equal(written, 0);
    // A run with zero admitted rows but a non-zero cap-rejection count must still say so:
    // `||`, never `&&` — the condition this test exists to pin.
    assert.deepEqual(lines, [
        { filename: COLLAPSED_SEEN_BASE_FILE, data: { summary: true, written: 0, truncated_by_cap: 40, timestamp: TS } },
    ]);
});

test("writeCollapsedSeenBase swallows a write failure instead of throwing", async () => {
    reset();
    context.jsonlWriter = { writeLine: async () => { throw new Error("disk full"); } } as unknown as JsonlWriter;
    context.qmCollapsed = [row("filter_on_seen")];

    await assert.doesNotReject(() => writeCollapsedSeenBase(TS));
});
