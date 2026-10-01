/**
 * Read-merge-write for the two route-loss audit sidecars (_questionmark_audit.json /
 * _diez_audit.json). A restart segment starts with EMPTY in-memory qmCollapsed /
 * diezCollapsed, so a blind write from its shutdown would clobber an earlier
 * segment's audit — merge with the on-disk file instead (existing rows first,
 * dedupe by `collapsed`, cap AUDIT_COLLAPSED_CAP). Fail-open: never throws —
 * an audit write must not break a shutdown.
 */
import fs from "node:fs";
import path from "node:path";

export const AUDIT_COLLAPSED_CAP = 200;

// origin/gate ride along undeclared since the qm_strip/facet_cap collector started tagging
// every row (collapsedSeenBase.ts's admission filter reads them). Optional, not required:
// rows merged back from an EARLIER segment's on-disk file predate that tagging and lack
// them — this type describes what a row MAY carry, not a guaranteed shape, and there is no
// migration backfilling the old ones.
type QmRow = { collapsed: string; base: string; param: string; origin?: string; gate?: string };
type DiezRow = { collapsed: string; base: string };
type PairStats = Record<string, { same: number; different: number; unusable: number }>;

/** Absent or corrupt file -> null (treated as absent). */
const readExisting = (file: string): any | null => {
    try {
        return JSON.parse(fs.readFileSync(file, "utf-8"));
    } catch {
        return null;
    }
};

/** Union, existing rows first (they win on duplicate `collapsed` keys), capped. */
const mergeCollapsed = <T extends { collapsed: string }>(existing: T[], current: T[]): T[] => {
    const out: T[] = [];
    const seen = new Set<string>();
    for (const row of [...existing, ...current]) {
        if (out.length >= AUDIT_COLLAPSED_CAP) break;
        if (!row || typeof row.collapsed !== "string" || seen.has(row.collapsed)) continue;
        seen.add(row.collapsed);
        out.push(row);
    }
    return out;
};

/**
 * Read-merge-write {storagePath}/_questionmark_audit.json. committed is unioned,
 * pair_stats summed per param per field. Skips the write when the merged result
 * is entirely empty (no empty sidecar on disk).
 */
export const writeQmAudit = (
    storagePath: string,
    current: { collapsed: QmRow[]; committed: string[]; pairStats: PairStats },
): { collapsedTotal: number } => {
    try {
        const file = path.join(storagePath, "_questionmark_audit.json");
        const existing = readExisting(file);
        const collapsed = mergeCollapsed<QmRow>(
            Array.isArray(existing?.collapsed_candidates) ? existing.collapsed_candidates : [],
            current.collapsed,
        );
        const committed = [...new Set<string>([
            ...(Array.isArray(existing?.committed) ? existing.committed : []),
            ...current.committed,
        ])];
        const pairStats: PairStats = {};
        const addStats = (src: PairStats | undefined) => {
            for (const [p, s] of Object.entries(src ?? {})) {
                const t = pairStats[p] ?? (pairStats[p] = { same: 0, different: 0, unusable: 0 });
                t.same += s?.same || 0;
                t.different += s?.different || 0;
                t.unusable += s?.unusable || 0;
            }
        };
        addStats(existing?.pair_stats);
        addStats(current.pairStats);
        if (collapsed.length === 0 && committed.length === 0 && Object.keys(pairStats).length === 0) {
            return { collapsedTotal: 0 };
        }
        fs.writeFileSync(file, JSON.stringify({
            collapsed_candidates: collapsed,
            committed,
            pair_stats: pairStats,
        }, null, 2));
        return { collapsedTotal: collapsed.length };
    } catch (e) {
        console.error("QM audit sidecar write failed:", e);
        return { collapsedTotal: 0 };
    }
};

/**
 * Read-merge-write {storagePath}/_diez_audit.json. content_collision: current
 * value wins when non-null, else the existing one is kept (the early shutdown
 * write passes null; the post-cleanDatasetFragments rewrite fills it in).
 */
export const writeDiezAudit = (
    storagePath: string,
    current: { collapsed: DiezRow[]; contentCollision: unknown | null },
): { collapsedTotal: number } => {
    try {
        const file = path.join(storagePath, "_diez_audit.json");
        const existing = readExisting(file);
        const collapsed = mergeCollapsed<DiezRow>(
            Array.isArray(existing?.collapsed_candidates) ? existing.collapsed_candidates : [],
            current.collapsed,
        );
        const contentCollision = current.contentCollision ?? existing?.content_collision ?? null;
        fs.writeFileSync(file, JSON.stringify({
            collapsed_candidates: collapsed,
            content_collision: contentCollision,
        }, null, 2));
        return { collapsedTotal: collapsed.length };
    } catch (e) {
        console.error("Diez audit sidecar write failed:", e);
        return { collapsedTotal: 0 };
    }
};

type CanonRow = { collapsed: string; base: string };

/**
 * Read-merge-write {storagePath}/_canonical_dedup_audit.json. Route-loss
 * candidates from the canonical ?param/# content-dedup pass, plus what the volume
 * guards REFUSED to collapse (oversized cells) or aborted (whole datasets) — a
 * refusal means that domain would have lost products, so it must not stay silent.
 * Skips the write only when there is nothing at all to report. Fail-open.
 */
export const writeCanonicalDedupAudit = (
    storagePath: string,
    current: {
        collapsed: CanonRow[]; removed: number; rewritten: number;
        refusedCells?: number; abortedDatasets?: string[];
    },
): { collapsedTotal: number } => {
    try {
        const file = path.join(storagePath, "_canonical_dedup_audit.json");
        const existing = readExisting(file);
        const collapsed = mergeCollapsed<CanonRow>(
            Array.isArray(existing?.collapsed_candidates) ? existing.collapsed_candidates : [],
            current.collapsed,
        );
        const refusedCells = (existing?.refused_cells || 0) + (current.refusedCells || 0);
        const abortedDatasets = [...new Set([
            ...(Array.isArray(existing?.aborted_datasets) ? existing.aborted_datasets : []),
            ...(current.abortedDatasets || []),
        ])];
        if (collapsed.length === 0 && refusedCells === 0 && abortedDatasets.length === 0) {
            return { collapsedTotal: 0 };
        }
        fs.writeFileSync(file, JSON.stringify({
            collapsed_candidates: collapsed,
            removed: (existing?.removed || 0) + current.removed,
            rewritten: (existing?.rewritten || 0) + current.rewritten,
            refused_cells: refusedCells,
            aborted_datasets: abortedDatasets,
        }, null, 2));
        return { collapsedTotal: collapsed.length };
    } catch (e) {
        console.error("Canonical dedup audit sidecar write failed:", e);
        return { collapsedTotal: 0 };
    }
};
