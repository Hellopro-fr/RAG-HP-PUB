import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { AUDIT_COLLAPSED_CAP, writeQmAudit, writeDiezAudit } from "./auditSidecars.js";

const mkTmp = () => fs.mkdtempSync(path.join(os.tmpdir(), "audit-sidecars-"));
const readJson = (dir: string, name: string) => JSON.parse(fs.readFileSync(path.join(dir, name), "utf-8"));

const QM_FILE = "_questionmark_audit.json";
const DIEZ_FILE = "_diez_audit.json";

test("writeQmAudit: fresh write creates the sidecar with all sections", () => {
    const dir = mkTmp();
    try {
        const res = writeQmAudit(dir, {
            collapsed: [{ collapsed: "https://x.fr/a?q=1", base: "https://x.fr/a", param: "q" }],
            committed: ["q"],
            pairStats: { q: { same: 3, different: 0, unusable: 1 } },
        });
        assert.equal(res.collapsedTotal, 1);
        const data = readJson(dir, QM_FILE);
        assert.deepEqual(data.collapsed_candidates, [{ collapsed: "https://x.fr/a?q=1", base: "https://x.fr/a", param: "q" }]);
        assert.deepEqual(data.committed, ["q"]);
        assert.deepEqual(data.pair_stats, { q: { same: 3, different: 0, unusable: 1 } });
    } finally {
        fs.rmSync(dir, { recursive: true, force: true });
    }
});

test("writeQmAudit: empty current preserves earlier segment's audit (restart clobber case)", () => {
    const dir = mkTmp();
    try {
        writeQmAudit(dir, {
            collapsed: [{ collapsed: "https://x.fr/a?q=1", base: "https://x.fr/a", param: "q" }],
            committed: ["q"],
            pairStats: { q: { same: 2, different: 1, unusable: 0 } },
        });
        // Second restart segment shuts down with EMPTY in-memory state.
        const res = writeQmAudit(dir, { collapsed: [], committed: [], pairStats: {} });
        assert.equal(res.collapsedTotal, 1);
        const data = readJson(dir, QM_FILE);
        assert.deepEqual(data.collapsed_candidates, [{ collapsed: "https://x.fr/a?q=1", base: "https://x.fr/a", param: "q" }]);
        assert.deepEqual(data.committed, ["q"]);
        assert.deepEqual(data.pair_stats, { q: { same: 2, different: 1, unusable: 0 } });
    } finally {
        fs.rmSync(dir, { recursive: true, force: true });
    }
});

test("writeQmAudit: merge dedupes by collapsed (existing row wins) and unions committed", () => {
    const dir = mkTmp();
    try {
        writeQmAudit(dir, {
            collapsed: [{ collapsed: "https://x.fr/a?q=1", base: "https://x.fr/a", param: "q" }],
            committed: ["q"],
            pairStats: {},
        });
        const res = writeQmAudit(dir, {
            collapsed: [
                { collapsed: "https://x.fr/a?q=1", base: "https://x.fr/DIFFERENT", param: "q" }, // dupe key
                { collapsed: "https://x.fr/b?p=2", base: "https://x.fr/b", param: "p" },
            ],
            committed: ["q", "p"],
            pairStats: {},
        });
        assert.equal(res.collapsedTotal, 2);
        const data = readJson(dir, QM_FILE);
        assert.deepEqual(data.collapsed_candidates, [
            { collapsed: "https://x.fr/a?q=1", base: "https://x.fr/a", param: "q" }, // existing first, kept
            { collapsed: "https://x.fr/b?p=2", base: "https://x.fr/b", param: "p" },
        ]);
        assert.deepEqual(data.committed, ["q", "p"]);
    } finally {
        fs.rmSync(dir, { recursive: true, force: true });
    }
});

test("writeQmAudit: cap enforced across merge, existing rows have priority", () => {
    const dir = mkTmp();
    try {
        const mkRows = (prefix: string, n: number) =>
            Array.from({ length: n }, (_, i) => ({ collapsed: `${prefix}${i}`, base: `b${i}`, param: "p" }));
        writeQmAudit(dir, { collapsed: mkRows("old", 150), committed: [], pairStats: {} });
        const res = writeQmAudit(dir, { collapsed: mkRows("new", 150), committed: [], pairStats: {} });
        assert.equal(res.collapsedTotal, AUDIT_COLLAPSED_CAP);
        const data = readJson(dir, QM_FILE);
        assert.equal(data.collapsed_candidates.length, AUDIT_COLLAPSED_CAP);
        // All 150 existing survive; only the first 50 new rows fit.
        assert.equal(data.collapsed_candidates[0].collapsed, "old0");
        assert.equal(data.collapsed_candidates[149].collapsed, "old149");
        assert.equal(data.collapsed_candidates[150].collapsed, "new0");
        assert.equal(data.collapsed_candidates[199].collapsed, "new49");
    } finally {
        fs.rmSync(dir, { recursive: true, force: true });
    }
});

test("writeQmAudit: pair_stats summed per param per field across segments", () => {
    const dir = mkTmp();
    try {
        writeQmAudit(dir, {
            collapsed: [], committed: [],
            pairStats: { q: { same: 2, different: 1, unusable: 0 }, ref: { same: 5, different: 0, unusable: 2 } },
        });
        writeQmAudit(dir, {
            collapsed: [], committed: [],
            pairStats: { q: { same: 3, different: 0, unusable: 4 }, page: { same: 1, different: 1, unusable: 1 } },
        });
        const data = readJson(dir, QM_FILE);
        assert.deepEqual(data.pair_stats, {
            q: { same: 5, different: 1, unusable: 4 },
            ref: { same: 5, different: 0, unusable: 2 },
            page: { same: 1, different: 1, unusable: 1 },
        });
    } finally {
        fs.rmSync(dir, { recursive: true, force: true });
    }
});

test("writeQmAudit: skips the write when both current and existing are empty", () => {
    const dir = mkTmp();
    try {
        const res = writeQmAudit(dir, { collapsed: [], committed: [], pairStats: {} });
        assert.equal(res.collapsedTotal, 0);
        assert.ok(!fs.existsSync(path.join(dir, QM_FILE)), "no empty sidecar should be created");
    } finally {
        fs.rmSync(dir, { recursive: true, force: true });
    }
});

test("writeQmAudit: corrupt existing file treated as absent", () => {
    const dir = mkTmp();
    try {
        fs.writeFileSync(path.join(dir, QM_FILE), "{not json!!");
        const res = writeQmAudit(dir, {
            collapsed: [{ collapsed: "https://x.fr/a?q=1", base: "https://x.fr/a", param: "q" }],
            committed: [],
            pairStats: {},
        });
        assert.equal(res.collapsedTotal, 1);
        const data = readJson(dir, QM_FILE);
        assert.equal(data.collapsed_candidates.length, 1);
        assert.deepEqual(data.committed, []);
        assert.deepEqual(data.pair_stats, {});
    } finally {
        fs.rmSync(dir, { recursive: true, force: true });
    }
});

test("writeDiezAudit: fresh write + merge preserves earlier candidates on empty current", () => {
    const dir = mkTmp();
    try {
        writeDiezAudit(dir, {
            collapsed: [{ collapsed: "https://x.fr/p#frag", base: "https://x.fr/p" }],
            contentCollision: null,
        });
        const res = writeDiezAudit(dir, { collapsed: [], contentCollision: null });
        assert.equal(res.collapsedTotal, 1);
        const data = readJson(dir, DIEZ_FILE);
        assert.deepEqual(data.collapsed_candidates, [{ collapsed: "https://x.fr/p#frag", base: "https://x.fr/p" }]);
        assert.equal(data.content_collision, null);
    } finally {
        fs.rmSync(dir, { recursive: true, force: true });
    }
});

test("writeDiezAudit: content_collision current-wins-else-existing", () => {
    const dir = mkTmp();
    try {
        // Segment 1 completed with real collision stats.
        writeDiezAudit(dir, {
            collapsed: [],
            contentCollision: { rewritten: 3, removed: 7, collisionsKept: 2 },
        });
        // A later segment's EARLY write (pre-cleanup) passes null → existing kept.
        writeDiezAudit(dir, { collapsed: [{ collapsed: "https://x.fr/q#f", base: "https://x.fr/q" }], contentCollision: null });
        let data = readJson(dir, DIEZ_FILE);
        assert.deepEqual(data.content_collision, { rewritten: 3, removed: 7, collisionsKept: 2 });
        assert.equal(data.collapsed_candidates.length, 1);
        // Post-cleanup rewrite with fresh stats → current wins.
        writeDiezAudit(dir, { collapsed: [], contentCollision: { rewritten: 1, removed: 0, collisionsKept: 9 } });
        data = readJson(dir, DIEZ_FILE);
        assert.deepEqual(data.content_collision, { rewritten: 1, removed: 0, collisionsKept: 9 });
        assert.equal(data.collapsed_candidates.length, 1, "candidates survive the stats rewrite");
    } finally {
        fs.rmSync(dir, { recursive: true, force: true });
    }
});

test("writeDiezAudit: dedupe by collapsed + cap across merge; corrupt existing treated as absent", () => {
    const dir = mkTmp();
    try {
        fs.writeFileSync(path.join(dir, DIEZ_FILE), " garbage");
        const mkRows = (prefix: string, n: number) =>
            Array.from({ length: n }, (_, i) => ({ collapsed: `${prefix}${i}`, base: `b${i}` }));
        let res = writeDiezAudit(dir, { collapsed: mkRows("a", 180), contentCollision: null });
        assert.equal(res.collapsedTotal, 180);
        // Overlapping keys a0..a179 + 40 new → dedupe then cap at 200.
        res = writeDiezAudit(dir, { collapsed: [...mkRows("a", 180), ...mkRows("z", 40)], contentCollision: null });
        assert.equal(res.collapsedTotal, AUDIT_COLLAPSED_CAP);
        const data = readJson(dir, DIEZ_FILE);
        assert.equal(data.collapsed_candidates.length, AUDIT_COLLAPSED_CAP);
        assert.equal(data.collapsed_candidates[0].collapsed, "a0");
        assert.equal(data.collapsed_candidates[180].collapsed, "z0");
        assert.equal(data.collapsed_candidates[199].collapsed, "z19");
    } finally {
        fs.rmSync(dir, { recursive: true, force: true });
    }
});
