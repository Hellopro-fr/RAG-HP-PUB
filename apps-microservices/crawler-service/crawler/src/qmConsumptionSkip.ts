/**
 * Part C (spec 2026-06-29): re-apply the LIVE strip to a dequeued request at
 * consumption time, so already-queued ?param=/# variants collapse to a seen base
 * and are skipped — the one-shot parseJsonFiles queue rewrite at commit is not
 * reliable against Crawlee's cached/head requests. Pure helpers (no Crawlee).
 */
import { createRequire } from "node:module";
import { context } from "./context.js";

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

/** Skip iff the strip changed the URL AND its stripped form is already known. */
export const shouldSkipDequeued = (url: string, strippedUrl: string, isKnown: boolean): boolean =>
    strippedUrl !== url && isKnown;

/** Record a collapsed candidate (route-loss audit). param = the single removed query key, else "". */
export const recordQmCollapsed = (collapsed: string, base: string): void => {
    if (context.qmCollapsed.length >= QM_COLLAPSED_CAP) return;
    let param = "";
    try {
        const c = new URL(collapsed).searchParams;
        const b = new URL(base).searchParams;
        const removed = [...c.keys()].filter((k) => !b.has(k));
        if (removed.length === 1) param = removed[0];
    } catch { /* keep "" */ }
    context.qmCollapsed.push({ collapsed, base, param });
};
