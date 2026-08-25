/**
 * Part C (spec 2026-06-29): re-apply the LIVE strip to a dequeued request at
 * consumption time, so already-queued ?param=/# variants collapse to a seen base
 * and are skipped — the one-shot parseJsonFiles queue rewrite at commit is not
 * reliable against Crawlee's cached/head requests. Pure helpers (no Crawlee).
 */
import { createRequire } from "node:module";
import { context } from "./context.js";
import { filterParamCollapseTarget } from "./filterOnSeen.js";

const _require = createRequire(import.meta.url);
const QM_COLLAPSED_CAP = 200;

/** Re-apply the live config strip to a URL (toRemove + skip/diez/per-class via processUrl). */
export const qmConsumptionStrip = (url: string): string => {
    try {
        const { processUrl } = _require("./functions.js");
        const { skipQuestionMark, skipDiez, toKeep, toRemove } = context.config;
        let out = url;
        if (toRemove && toRemove.length > 0) out = processUrl(out, false, false, { toRemove });
        if (skipQuestionMark || skipDiez) {
            const params: { toKeep?: string[]; toRemove?: string[] } = {};
            if (toKeep && toKeep.length > 0) params.toKeep = toKeep;
            if (toRemove && toRemove.length > 0) params.toRemove = toRemove;
            out = processUrl(out, skipQuestionMark, skipDiez, params);
        }
        return out;
    } catch {
        return url;
    }
};

/** Where a skipnav collapse target came from — the two branches do NOT prove the same
 * thing, so the caller must be able to tell them apart. 'none' = neither decided, and
 * the target is then the URL itself (a degenerate entry: never usable downstream). */
export type CollapseVia = 'qm_strip' | 'filter_on_seen' | 'none';

/** Best-effort collapse target for a request flagged skipNavigation on disk (D1).
 * Mirrors the D1 flag deciders in main.ts: processUrl-strip first, filter-on-seen second.
 * Reports WHICH branch decided: a toRemove strip is content-proven (QM tier-2 committed
 * it on a Jaccard majority), filter-on-seen is structural (the base was in seenBases).
 * Collapsing them under one label would let a consumer act on the weaker evidence while
 * believing it had the stronger. */
export const skipnavCollapseTarget = (
    url: string,
    seenBases: Set<string>,
): { target: string; via: CollapseVia } => {
    const stripped = qmConsumptionStrip(url);
    if (stripped !== url) return { target: stripped, via: 'qm_strip' };
    const t = filterParamCollapseTarget(url, seenBases);
    if (t) return { target: t, via: 'filter_on_seen' };
    return { target: url, via: 'none' };
};

/** Skip iff the strip changed the URL AND its stripped form is already known. */
export const shouldSkipDequeued = (url: string, strippedUrl: string, isKnown: boolean): boolean =>
    strippedUrl !== url && isKnown;

/** Which decider produced a collapse — carries the proof strength downstream. */
export type CollapseOrigin = 'qm_strip' | 'facet_cap' | 'filter_on_seen';
/** When it fired — 'prenav' covers three deciders, 'filter_on_seen' covers two moments,
 * so neither field can be derived from the other. */
export type CollapseGate = 'prenav' | 'dequeue' | 'enqueue';

const foldSlash = (u: string): string => u.replace(/\/+$/, "");

/** Record a collapsed candidate (route-loss audit). param = the single removed query key,
 * else "". Refuses a DEGENERATE entry (base === collapsed modulo trailing slash): it would
 * mean "this fiche is a duplicate of itself", and a consumer applying it would retire the
 * fiche with no replacement. Counts what the cap refuses so a truncated collection cannot
 * be read as an exhaustive one. */
export const recordQmCollapsed = (
    collapsed: string,
    base: string,
    origin: CollapseOrigin,
    gate: CollapseGate,
): void => {
    if (foldSlash(collapsed) === foldSlash(base)) return;
    if (context.qmCollapsed.length >= QM_COLLAPSED_CAP) {
        context.qmCollapsedRejected++;
        return;
    }
    let param = "";
    try {
        const c = new URL(collapsed).searchParams;
        const b = new URL(base).searchParams;
        const removed = [...c.keys()].filter((k) => !b.has(k));
        if (removed.length === 1) param = removed[0];
    } catch { /* keep "" */ }
    context.qmCollapsed.push({ collapsed, base, param, origin, gate });
};
