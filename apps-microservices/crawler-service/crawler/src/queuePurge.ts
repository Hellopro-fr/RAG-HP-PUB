/**
 * Queue-purge (D1): before RequestQueue.open, flag already-queued stale variants
 * with skipNavigation so they are dropped without a fetch at dispatch (handler
 * early-guard). Disk-only + loss-proof: the "known base" anchor is the set of
 * already-handled files on disk. Never touches orderNo/uniqueKey/id, so pending/
 * handled/total counts stay consistent (repairQueueMetadata runs after). Strip is
 * injected so this module stays crawlee-free (loadable under tsx --test).
 *
 * ANCHOR NOTE: "handled" on disk means Crawlee finished the request — success OR
 * retries-exhausted. So a variant whose collapsed base FAILED terminally last run
 * is still flagged skipNavigation here (skipped this run), unlike the mid-run A /
 * C2 paths which anchor on the Redis success-set. Deliberate: the committed
 * decision declared these variants the same page, a failed base implies the
 * variant fails too, and the next scheduled crawl retries. Kept disk-only for
 * self-containment (no Redis dependency at startup).
 *
 * MARK-HANDLED (A517 Brief 2, QUEUE_PURGE_MARK_HANDLED_ENABLED, default off): a variant
 * flagged here but left pending is still dequeued by Crawlee one by one, and each dequeue
 * costs ~1 s (the browser crawler opens a tab before it tests skipNavigation): 587,764
 * variants took ~8.8 days on one MAJ. With the flag on, orderNo IS rewritten: each variant
 * flagged here is also written handled (orderNo null at the root; handledAt in the inner
 * json, so a later rewrite of the request keeps it handled), and a request still pending
 * with skipNavigation from a previous start is converted the same way. Same end state as
 * the dequeue path, without the dequeues. A converted request does not enter the canonical
 * set: when no handled file anchors its base, a later variant of that base is kept rather
 * than flagged (conservative: fetched once, then deduped live). Flag off -> exactly the
 * previous behaviour (byte-identical writes).
 */
import * as fs from "node:fs";
import * as path from "node:path";

const isPending = (orderNo: unknown): boolean =>
    typeof orderNo === "number" && Number.isFinite(orderNo);

/** Kill-switch, read at call time (not memoized), like facetFragmentStripEnabled. */
export const queuePurgeMarkHandledEnabled = (): boolean =>
    (process.env.QUEUE_PURGE_MARK_HANDLED_ENABLED ?? "false").toLowerCase() === "true";

/** skipNavigation already set on disk by a previous start (root or inner json). */
const isFlaggedSkipNav = (obj: any): boolean => {
    if (obj?.userData?.__crawlee?.skipNavigation === true) return true;
    try { return JSON.parse(obj.json)?.userData?.__crawlee?.skipNavigation === true; } catch { return false; }
};

/** memory-storage "handled": orderNo null at the root (listAndLockHead skips it, queueRepair
 * counts it handled) + handledAt in the inner json (_calculateOrderNo keeps null on rewrite). */
const markHandledOnDisk = (obj: any, handledAt: string): void => {
    obj.orderNo = null;
    try {
        const inner = JSON.parse(obj.json);
        inner.handledAt = handledAt;
        obj.json = JSON.stringify(inner);
    } catch { /* inner missing/malformed: root orderNo null still makes it handled */ }
};

export const flagStaleVariantsOnDisk = (
    queueDir: string,
    stripFn: (url: string) => string,
    extraSkip?: (url: string) => boolean,
    onMarkedHandled?: (url: string) => void,
): { flagged: number; kept: number; markedHandled: number } => {
    let flagged = 0;
    let kept = 0;
    let markedHandled = 0;
    const markHandled = queuePurgeMarkHandledEnabled();
    const handledAt = new Date().toISOString();
    const notify = (url: string): void => {
        try { onMarkedHandled?.(url); } catch { /* best-effort: never blocks the purge */ }
    };
    let names: string[];
    try {
        names = fs.readdirSync(queueDir);
    } catch {
        return { flagged, kept, markedHandled };
    }

    type Rec = { file: string; obj: any };
    const pending: Rec[] = [];
    const canonical = new Set<string>();

    for (const name of names) {
        if (!name.endsWith(".json") || name === "__metadata__.json" || name.startsWith(".")) continue;
        const file = path.join(queueDir, name);
        let obj: any;
        try {
            obj = JSON.parse(fs.readFileSync(file, "utf-8"));
        } catch {
            continue; // memory-storage ignores unparseable files too
        }
        if (isPending(obj.orderNo)) {
            pending.push({ file, obj });
        } else {
            try { canonical.add(stripFn(obj.url)); } catch { /* skip */ }
        }
    }

    for (const { file, obj } of pending) {
        if (markHandled && isFlaggedSkipNav(obj)) {
            // Flagged by a previous start, still pending: handled now, kept OUT of canonical.
            markHandledOnDisk(obj, handledAt);
            fs.writeFileSync(file, JSON.stringify(obj, null, 2));
            markedHandled++;
            notify(obj.url);
            continue;
        }
        let stripped: string;
        try { stripped = stripFn(obj.url); } catch { kept++; continue; }
        // Queue-purge #2 hook: extraSkip is a second, independent stale-variant
        // decider (e.g. filter-on-seen-base). Omitted -> condition below is
        // byte-identical to the original stripFn-only check.
        const staleByExtra = Boolean(extraSkip && extraSkip(obj.url));
        if ((stripped !== obj.url && canonical.has(stripped)) || staleByExtra) {
            obj.userData = obj.userData ?? {};
            obj.userData.__crawlee = obj.userData.__crawlee ?? {};
            obj.userData.__crawlee.skipNavigation = true;
            try {
                const inner = JSON.parse(obj.json);
                inner.userData = inner.userData ?? {};
                inner.userData.__crawlee = inner.userData.__crawlee ?? {};
                inner.userData.__crawlee.skipNavigation = true;
                obj.json = JSON.stringify(inner);
            } catch { /* inner missing/malformed: root flag still applies */ }
            if (markHandled) markHandledOnDisk(obj, handledAt);
            fs.writeFileSync(file, JSON.stringify(obj, null, 2));
            flagged++;
            if (markHandled) {
                markedHandled++;
                notify(obj.url);
            }
        } else {
            canonical.add(stripped);
            kept++;
        }
    }
    return { flagged, kept, markedHandled };
};
