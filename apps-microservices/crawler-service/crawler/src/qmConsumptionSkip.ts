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
/** Budget for the ADMITTED origin only (filter_on_seen) — separate from the shared 200
 * above so facet_cap/qm_strip (audit-only, never read by the BO) can never starve the one
 * channel collapsed_seen_base.jsonl carries. Sized on measurement: the largest collapsible
 * population found on a single domain was 2,884 URLs, and the BO-side cap consuming this
 * file is set to 4000 on that basis — a lower crawler-side ceiling would make that cap
 * unreachable. */
const SEEN_BASE_COLLAPSED_CAP = 4000;

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

/**
 * Clears the THREE fields that must always move together: the row array and the two dedup
 * maps.
 *
 * Exported rather than left to each caller because a PARTIAL reset is a silent trap —
 * emptying `qmCollapsed` while the key maps keep their entries makes every later record of
 * those pairs a no-op, with no counter moving and no log. The test helper in
 * qmConsumptionSkip.test.ts did exactly that on the first draft of this change. Production
 * has no reassignment of `qmCollapsed` today (a restart gets fresh module state instead), so
 * this exists to keep it that way rather than to fix a live path.
 */
export const resetQmCollapsedState = (): void => {
    context.qmCollapsed = [];
    context.qmCollapsedRejected = 0;
    context.qmCollapsedSeenKeys.clear();
    context.qmCollapsedOtherKeys.clear();
};

/** Record a collapsed candidate (route-loss audit). param = the single removed query key,
 * else "". Refuses a DEGENERATE entry (base === collapsed modulo trailing slash): it would
 * mean "this fiche is a duplicate of itself", and a consumer applying it would retire the
 * fiche with no replacement. Counts what the cap refuses so a truncated collection cannot
 * be read as an exhaustive one.
 *
 * THE CAP BOUNDS A POPULATION, NOT A CALL COUNT — a repeat of a pair already recorded is
 * dropped before the cap is consulted, so it neither takes a slot nor reports a truncation.
 * MEASURED 2026-09-02, which is why this is not a micro-optimisation: `filter_on_seen` is
 * recorded from THREE sites (functions.ts prenav, routes.ts dequeue, routes.ts enqueue) and
 * the last sits inside the enqueue loop, so one parameterised link in a nav menu is recorded
 * once per crawled page. On tools-trails.com that produced 45,662 records for FOUR distinct
 * pairs, and on maneko.fr 5,389 for ONE. The 4000 budget filled with repeats, every further
 * record incremented `qmCollapsedRejected`, and the BO shut the whole destructive phase of
 * the run on that false truncation — losing redirections and Milvus orphan handling that had
 * nothing to do with this channel. Four domains sat blocked for up to five days.
 *
 * The sibling consumer already did this: auditSidecars.ts's mergeCollapsed() dedupes by
 * `collapsed` and spends its own 200 budget on distinct rows only. The collector was the one
 * end that did not. */
export const recordQmCollapsed = (
    collapsed: string,
    base: string,
    origin: CollapseOrigin,
    gate: CollapseGate,
): void => {
    if (foldSlash(collapsed) === foldSlash(base)) return;
    const isSeenBase = origin === 'filter_on_seen';
    const cap = isSeenBase ? SEEN_BASE_COLLAPSED_CAP : QM_COLLAPSED_CAP;
    // One map per cap class, so `size` answers for THIS class in O(1). It also replaces a
    // `.filter().length` recomputed over the whole array on every call — quadratic in the
    // number of calls, and at 45,662 calls against a 4000-element array that is ~180M
    // comparisons in one run.
    const keys = isSeenBase ? context.qmCollapsedSeenKeys : context.qmCollapsedOtherKeys;
    // NUL cannot occur in a URL. Without an impossible separator, ("a", "b/c") and ("a/b",
    // "c") would share a key.
    const key = `${foldSlash(collapsed)}\u0000${foldSlash(base)}`;
    // ⚠⚠ THE DEDUP TEST COMES BEFORE THE CAP, AND THAT ORDER *IS* THE FIX. Reversed, a
    // repeat arriving after the cap was reached would increment `qmCollapsedRejected` —
    // declaring to the BO a truncation the population never suffered. That is precisely the
    // defect measured on 2026-09-02; see the docblock above.
    if (keys.has(key)) return;
    if (keys.size >= cap) {
        // Only filter_on_seen feeds truncated_by_cap: it is the sole origin the BO reads,
        // so a facet_cap/qm_strip refusal never cost the admitted channel anything.
        if (isSeenBase) context.qmCollapsedRejected++;
        return;
    }
    let param = "";
    try {
        const c = new URL(collapsed).searchParams;
        const b = new URL(base).searchParams;
        const removed = [...c.keys()].filter((k) => !b.has(k));
        if (removed.length === 1) param = removed[0];
    } catch { /* keep "" */ }
    // Added at the push, not at the cap test: the invariant this fix rests on is
    // `keys.size === (rows of that class in qmCollapsed)`, and only adjacency keeps it true.
    keys.add(key);
    context.qmCollapsed.push({ collapsed, base, param, origin, gate });
};
