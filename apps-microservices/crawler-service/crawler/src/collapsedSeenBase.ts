/**
 * The BO-facing view of context.qmCollapsed: only the collapses whose BASE WAS CRAWLED.
 *
 * The admission criterion is NOT "structural". facet_cap is structural too, and it
 * records pathBaseKey(url) — a base it never verified — so admitting it would let the BO
 * retire a fiche in favour of a base nobody observed. qm_strip is content-proven but by a
 * different mechanism (a QM tier-2 toRemove commit), and its base is known to Redis dedup,
 * not to seenBases. Only filter_on_seen proves, by seenBases, that the base was crawled.
 *
 * Named after the criterion rather than the family so its name cannot be read as an
 * invitation to widen it.
 */
import { context } from "./context.js";
import type { CollapseOrigin, CollapseGate } from "./qmConsumptionSkip.js";

export type CollapsedRow = {
    collapsed: string; base: string; param: string; origin: CollapseOrigin; gate: CollapseGate;
};

const foldSlash = (u: string): string => u.replace(/\/+$/, "");

/** Pure. Second degeneracy check on purpose: the collector already refuses these, but a
 * guard at one end only holds while the other end is deployed. */
export const selectSeenBaseRows = (rows: CollapsedRow[]): CollapsedRow[] =>
    rows.filter((r) => r
        && r.origin === "filter_on_seen"
        && typeof r.collapsed === "string" && typeof r.base === "string"
        && foldSlash(r.collapsed) !== foldSlash(r.base));

export const COLLAPSED_SEEN_BASE_FILE = "collapsed_seen_base.jsonl";

/** Fire-and-forget. No-op outside update mode (no jsonlWriter). Never throws: a sidecar
 * write must not fail an otherwise healthy crawl. */
export const writeCollapsedSeenBase = async (timestamp: string): Promise<number> => {
    const writer = context.jsonlWriter;
    if (!writer) return 0;
    const rows = selectSeenBaseRows(context.qmCollapsed);
    try {
        for (const r of rows) {
            await writer.writeLine(COLLAPSED_SEEN_BASE_FILE, {
                url: r.collapsed, base: r.base, param: r.param,
                origin: r.origin, gate: r.gate, timestamp,
            });
        }
        // Summary line, written even at zero rows when the cap refused entries: a silent
        // cap reads as "there was nothing more to clean".
        if (rows.length > 0 || context.qmCollapsedRejected > 0) {
            await writer.writeLine(COLLAPSED_SEEN_BASE_FILE, {
                summary: true, written: rows.length,
                truncated_by_cap: context.qmCollapsedRejected, timestamp,
            });
        }
    } catch (e) {
        console.error("collapsed_seen_base sidecar write failed:", e);
    }
    return rows.length;
};
